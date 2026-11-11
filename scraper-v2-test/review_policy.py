"""Copy-only review policy. Never converts keyword matching into qualification.
Company history is an exception gate, NOT a display block. Exact req dedupe is
separate. Human review decisions are bound to exact req URL and title/raw-JD digest.
The complete ledger is externally hash-pinned for reproducible output, not consent.
Nothing here authorizes an application or an external message.
"""
import hashlib,json
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from screen_policy import company,clean,load_policy,pinned

def canonical_url(v):
 try:
  u=urlsplit(v)
  if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):return None
  path=u.path.rstrip('/')
  # Only provider-known UI suffixes are removable, never arbitrary URL paths.
  if u.hostname=='jobs.ashbyhq.com' and path.endswith('/application'):path=path[:-12]
  if u.hostname=='jobs.lever.co' and path.endswith('/apply'):path=path[:-6]
  query=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('gh_src','lever-source','source')]
  return urlunsplit(('https',u.hostname.lower(),path,urlencode(sorted(query)),''))
 except (TypeError,ValueError):return None

def jd_sha256(job):
 # Hash exact title and raw provider description, not a renderer's text scrape.
 if not isinstance(job.get('description'),str) or not job['description']:return None
 return digest({'title':job.get('title'),'description':job['description']})

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def validate(p):
 if not isinstance(p,dict) or set(p)!={'schema','provenance','applications','company_exceptions','reviewed_jobs','hide_companies'} or p['schema']!=2:raise ValueError('Invalid review policy')
 if not isinstance(p['provenance'],list) or not p['provenance'] or any(not isinstance(x,str) or not x for x in p['provenance']):raise ValueError('Policy provenance required')
 for name in ['applications','company_exceptions','reviewed_jobs','hide_companies']:
  if not isinstance(p[name],list):raise ValueError('Expected list '+name)
 for a in p['applications']:
  if not isinstance(a,dict) or not company(a.get('company')) or not a.get('evidence'):raise ValueError('Application evidence required')
  if a.get('url') and not canonical_url(a['url']):raise ValueError('Invalid application URL')
  if a.get('job_key') is not None and (not isinstance(a['job_key'],str) or not a['job_key']):raise ValueError('Invalid application key')
 for e in p['company_exceptions']:
  if not isinstance(e,dict) or not company(e.get('company')) or not canonical_url(e.get('url')) or not e.get('owner_evidence'):raise ValueError('Exception must be exact req and owner sourced')
 seen=set()
 for r in p['reviewed_jobs']:
  if not isinstance(r,dict) or not canonical_url(r.get('url')) or r.get('decision') not in ['REVIEWED_MATCH','EXCLUDE','HOLD'] or not r.get('evidence') or not isinstance(r.get('jd_sha256'),str) or len(r['jd_sha256'])!=64 or any(c not in '0123456789abcdef' for c in r['jd_sha256']):raise ValueError('Invalid reviewed job')
  u=canonical_url(r['url'])
  if u in seen:raise ValueError('Duplicate canonical review URL')
  seen.add(u)
 for h in p['hide_companies']:
  if not isinstance(h,dict) or not company(h.get('company')) or not h.get('owner_evidence'):raise ValueError('Display hiding requires explicit owner evidence')
 return digest(p)

def assess(j,p):
 ph=validate(p);url=canonical_url(j.get('job_url'));co=company(j.get('company'));reasons=[]
 out={'key':clean(j.get('key'),512),'url':url,'company':clean(j.get('company'),200),'title':clean(j.get('title'),300),'policy_sha256':ph,'qualification_state':'NOT_ASSESSED','state':'NEEDS_REVIEW','reasons':reasons,'visible':True,'application_authority':False}
 if not co or not url:reasons.append('IDENTITY_UNVERIFIED')
 if any(company(h['company'])==co for h in p['hide_companies']):out['visible']=False;reasons.append('OWNER_DISPLAY_HIDE')
 if j.get('ats')=='agency' or '(agency)' in str(j.get('company','')).casefold():reasons.append('HIRING_EMPLOYER_UNVERIFIED')
 if any((a.get('job_key') and a['job_key']==j.get('key')) or (url and a.get('url') and canonical_url(a['url'])==url) for a in p['applications']):out['state']='ALREADY_APPLIED';reasons.append('EXACT_REQ_APPLICATION');return out
 prior=any(company(a['company'])==co for a in p['applications'])
 exception=any(company(e['company'])==co and canonical_url(e['url'])==url for e in p['company_exceptions'])
 if prior and not exception:reasons.append('PRIOR_COMPANY_REQUIRES_OWNER_EXCEPTION')
 if j.get('irish_location_match') is not True or j.get('remote_ireland_eligibility_unverified'):reasons.append('IRISH_LOCATION_UNVERIFIED')
 if j.get('active') is not True or j.get('stale') is not False:reasons.append('LIVE_AVAILABILITY_UNVERIFIED')
 if j.get('description_state') not in ['PRESENT','CACHED'] or j.get('description_freshness') not in ['LIVE_FEED','FRESH_CACHE','FRESH_DETAIL']:reasons.append('FULL_CURRENT_JD_UNVERIFIED')
 jd=jd_sha256(j)
 review=[r for r in p['reviewed_jobs'] if canonical_url(r['url'])==url]
 if len(review)>1:raise ValueError('Ambiguous review for '+str(url))
 if review:
  r=review[0]
  if r['jd_sha256']!=jd:reasons.append('JD_CHANGED_SINCE_REVIEW')
  elif r['decision']=='EXCLUDE':out['state']='EXCLUDED';out['qualification_state']='REVIEWED_EXCLUSION';reasons.append('SOURCED_ROLE_EXCLUSION')
  elif r['decision']=='HOLD':reasons.append('SOURCED_ROLE_HOLD')
  elif not reasons:out['state']='REVIEWED_MATCH';out['qualification_state']='REVIEWED_MATCH'
 else:reasons.append('SEMANTIC_FIT_AND_PAY_NOT_REVIEWED')
 return out

def build_digest(jobs,p,expected_policy_sha256=None,screen_policy=None,expected_screen_sha256=None):
 ph=validate(p)
 if expected_policy_sha256!=ph:raise ValueError('Externally pinned policy digest required')
 screened=pinned(screen_policy,expected_screen_sha256)
 rows=[]
 for j in jobs:
  # This API consumes source-state rows, never display.json or raw UI projections.
  if not isinstance(j,dict) or any(k not in j for k in ['active','stale','description','irish_location_match']):raise ValueError('Full source-state row required')
  # Recruiting agencies do not establish the hiring employer, so no UI review row.
  if j.get('ats')=='agency' or '(agency)' in str(j.get('company','')).casefold():continue
  if not company(j.get('company')) or company(j.get('company')) in screened['blocked']:continue
  r=assess(j,p)
  if r['visible']:rows.append(r)
 counts={}
 for r in rows:counts[r['state']]=counts.get(r['state'],0)+1
 return {'schema':2,'policy_sha256':ph,'screen_policy_sha256':screened['sha256'],'application_authority':False,'counts':counts,'jobs':rows,'disclaimer':'Review candidates are not qualified jobs. Company history is not a blanket display block. No external action is authorized.'}
