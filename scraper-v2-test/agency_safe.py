"""Copy-only agency parser and incremental state engine. No production wiring.
Locations are accepted only from JobPosting structured data. No footer inference.
"""
import json,re,html,hashlib,time,pathlib
from html.parser import HTMLParser
import ingest
class Parser(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.in_ld=False;self.scripts=[];self.parts=[];self.skip=0;self.title=False;self.titleparts=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag in ('script','style'):self.skip+=1
  if tag=='script'and'ld+json'in(a.get('type')or'').lower():self.in_ld=True;self.parts=[]
  if tag=='title':self.title=True
 def handle_endtag(self,tag):
  if tag=='script'and self.in_ld:self.scripts.append(''.join(self.parts));self.in_ld=False
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
  if tag=='title':self.title=False
 def handle_data(self,data):
  if self.in_ld:self.parts.append(data)
  if self.title:self.titleparts.append(data)
def objects(x):
 if isinstance(x,list):
  for v in x:yield from objects(v)
 elif isinstance(x,dict):
  t=x.get('@type');ts=t if isinstance(t,list)else[t]
  if 'JobPosting'in ts:yield x
  if '@graph'in x:yield from objects(x['@graph'])
def plain(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s or''))).strip()
def location(record):
 out=[];locs=record.get('jobLocation',[]);locs=locs if isinstance(locs,list)else[locs]
 for loc in locs:
  if not isinstance(loc,dict):continue
  a=loc.get('address',{})
  if not isinstance(a,dict):continue
  country=a.get('addressCountry','');country=country.get('name','')if isinstance(country,dict)else country
  if isinstance(country,str)and country.strip().upper()in('IE','IRL'):country='Ireland'
  fields=[a.get('addressLocality',''),a.get('addressRegion',''),country]
  out.append(', '.join(x for x in fields if isinstance(x,str)and x))
 return '; '.join(out)
def parse_page(source,url,text,now=None):
 p=Parser();p.feed(text);records=[]
 for s in p.scripts:
  try:records.extend(objects(json.loads(s)))
  except (ValueError,TypeError):continue
 records=list({json.dumps(x,sort_keys=True):x for x in records}.values())
 if not records:
  from agency_html import extract
  scoped=extract(source,url,text)
  if scoped:records=[scoped]
 if not records:return {'job_url':url,'company':source,'title':''.join(p.titleparts).strip(),'description_state':'UNVERIFIED','irish_location_match':False,'location_state':'UNVERIFIED','active_state':'UNVERIFIED'}
 # Multiple structured jobs on one URL are not silently bound to the first.
 if len(records)!=1:raise ValueError('Ambiguous multiple JobPosting records')
 r=records[0];desc=plain(r.get('description',''));loc=location(r)
 if len(desc)>2*1024*1024:raise ValueError('Description exceeds safe limit; no silent truncation')
 country_parts=loc.replace(', IE',', Ireland').replace(', IRL',', Ireland')
 explicit_countries=[]
 for entry in r.get('jobLocation',[])if isinstance(r.get('jobLocation',[]),list)else[r.get('jobLocation')]:
  if isinstance(entry,dict)and isinstance(entry.get('address'),dict):
   country=entry['address'].get('addressCountry');country=country.get('name')if isinstance(country,dict)else country
   if isinstance(country,str)and country.strip():explicit_countries.append(country.strip().casefold())
 country_allowed=not explicit_countries or any(c in ['ie','irl','ireland','republic of ireland']for c in explicit_countries)
 if not explicit_countries:country_allowed=bool(re.search(r'\b(Ireland|Republic of Ireland)\b|\b(?:Co\.|County)\s+[A-Z][a-z]+',loc))
 valid=r.get('validThrough');active='LISTED'if valid is None or isinstance(valid,str)else'UNVERIFIED'
 if isinstance(valid,str):
  from datetime import datetime,timezone
  try:
   expiry=datetime.fromisoformat(valid.replace('Z','+00:00'))
   if len(valid)==10:expiry=expiry.replace(hour=23,minute=59,second=59,tzinfo=timezone.utc)
   elif expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
   if expiry.tzinfo is not None and expiry.timestamp()<(now or time.time()):active='EXPIRED_DECLARED'
  except (ValueError,TypeError):active='UNVERIFIED'
 return {'key':'agency:'+source+':'+hashlib.sha256(url.encode()).hexdigest()[:24],'company':source+' (agency)','job_url':url,'title':plain(r.get('title','')),'location':loc,'description':desc,'description_state':'PRESENT'if desc else'MISSING','description_completeness':'UNVERIFIED','irish_location_match':country_allowed and bool(ingest.irish_location(country_parts)),'location_state':r.get('_evidence','PUBLISHER_DECLARED')if loc else'UNVERIFIED','active_state':active,'review_state':'NOT_REVIEWED'}
def update(state,source,urls,complete,fetcher,now=None,max_details=150,refresh_after=86400):
 now=time.time()if now is None else now;state=json.loads(json.dumps(state));rows=state.setdefault('jobs',{});changes=[];errors=[];urls=set(urls)
 due=[u for u in urls if now>=rows.get(u,{}).get('next_attempt_at',0)and(u not in rows or now-rows[u].get('checked_at',0)>=refresh_after or rows[u].get('last_error'))]
 # Older attempts go first. Failed rows advance their attempt clock and back off.
 due.sort(key=lambda u:(rows.get(u,{}).get('last_attempt_at',0),u))
 for u in due[:max_details]:
  prior=rows.get(u)
  try:
   row=parse_page(source,u,fetcher(u),now)
   if row.get('description_state')=='UNVERIFIED':raise ValueError('Page has no verified JobPosting')
   sig=hashlib.sha256(json.dumps({k:v for k,v in row.items()if k not in ['checked_at','availability']},sort_keys=True).encode()).hexdigest()
   row.update(checked_at=now,last_success_at=now,last_attempt_at=now,next_attempt_at=now+refresh_after,hash=sig,availability='LISTED',description_freshness='LIVE_DETAIL',attempts=0)
   rows[u]=row
   if prior is None or prior.get('hash')!=sig:changes.append({'url':u,'kind':'NEW'if prior is None else'CHANGED'})
  except Exception as e:
   from urllib.error import HTTPError
   errors.append({'url':u,'error':type(e).__name__});row=rows.setdefault(u,{'job_url':u});attempts=row.get('attempts',0)+1
   row.update(last_error=type(e).__name__,last_attempt_at=now,attempts=attempts,next_attempt_at=now+min(86400,300*2**min(attempts-1,9)))
   if row.get('description'):row.update(description_state='CACHED',description_freshness='STALE_CACHE')
   if isinstance(e,HTTPError)and e.code in(404,410):row['availability']='DETAIL_GONE_UNVERIFIED'
 for u in urls:
  if u in rows:
   rows[u].pop('absent_since',None)
   if rows[u].get('availability')=='NOT_IN_LATEST_SITEMAP_UNVERIFIED':rows[u]['availability']='LISTED'
 if complete:
  for u,r in rows.items():
   if u not in urls:r['availability']='NOT_IN_LATEST_SITEMAP_UNVERIFIED';r.setdefault('absent_since',now)
   else:r.pop('absent_since',None)
 # Old absent descriptions are removed, records retain uncertain closure metadata.
 for r in rows.values():
  if now-r.get('absent_since',now)>30*86400:
   r.pop('description',None);r.update(description_state='MISSING',description_freshness='ARCHIVED_ABSENT')
 return state,{'changes':changes,'errors':errors,'backlog':max(0,len(due)-max_details),'sitemap_complete':complete}
