"""GET-only local employer-feed ingestion. No applications, mail or production writes."""
import argparse, hashlib, json, pathlib, re, time, urllib.request, urllib.error
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

IRISH = re.compile(r'\b(ireland|dublin|cork|galway|limerick|waterford|kilkenny|athlone|tralee|kildare|naas|leixlip|maynooth|drogheda|dundalk|letterkenny|sligo|cavan|ennis|shannon|castlebar|tullamore|mullingar|wexford|wicklow|carlow|nenagh|clonmel|dun laoghaire|dún laoghaire|ballincollig|swords|tallaght|bray|portlaoise|dungarvan|tipperary|meath|donegal|leopardstown)\b',re.I)
NORTHERN = re.compile(r'\b(northern ireland|belfast|derry|antrim|newry)\b',re.I)
US_STATES='AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.replace(' ','|')
# foreign markers: US/Canada/Australia names, US state codes (case-sensitive so 'in'/'or'/'me' never count), and feed prefixes like US-CA-Dublin
FOREIGN_DUBLIN = re.compile(r'\b(ohio|california|pennsylvania|texas|georgia|virginia|florida|united states|usa|us|canada|australia|new zealand)\b|(?-i:(?:^|[\s,-])(?:'+US_STATES+r')(?:$|[\s,-]))|\b[A-Z]{2}-(?:[A-Z]{2}-)?Dublin\b',re.I)

def irish_location(loc):
    parts=re.split(r'[;|/]|\s+(?:or|and)\s+',loc,flags=re.I)
    def ok(part):
        if not IRISH.search(part) or NORTHERN.search(part): return False
        if re.search(r'\bireland\b',part,re.I): return True   # explicit country evidence wins
        return not FOREIGN_DUBLIN.search(part)
    return any(ok(part) for part in parts)

def retry_delay(error, default=3600):
    # Respect a rate-limit/server Retry-After; never retry within this run.
    value = error.headers.get('Retry-After') if isinstance(error,urllib.error.HTTPError) and error.headers else None
    if value:
        try: return max(default,int(value))
        except ValueError:
            try: return max(default,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
            except (ValueError,TypeError): pass
    return default

LANES = re.compile(r'\b(operations?|operational|project|program(me)?|pmo|business|strategy|strategic|analyst|coordinat\w*|implementation|onboarding|customer|client|enablement|supply|procurement|planning|quality|process|partnership|commercial|founder|chief of staff|account|revenue)\b', re.I)

def remote_ireland_pending(loc, ireland=False):
    if ireland or NORTHERN.search(loc): return False
    if not re.search(r'\b(remote|emea|europe|european union|worldwide)\b',loc,re.I): return False
    # Broad regions still need employer confirmation; named foreign-country-only remote is not an Ireland lead.
    if re.search(r'\b(emea|europe|european union|worldwide|global)\b',loc,re.I): return True
    if re.search(r'\b(north america|united states|usa|us|u\.s\.|canada|united kingdom|uk|germany|france|spain|italy|netherlands|australia|india|singapore|boston|new york|california|ohio)\b',loc,re.I): return False
    return True

def posted_utc(value, semantics):
    if value is None: return None
    try:
        if semantics=='createdAt_epoch_ms': return datetime.fromtimestamp(float(value)/1000,timezone.utc).isoformat()
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:return None
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError,TypeError,OverflowError): return None

NON_CHANGE_KEYS={'remote_ireland_eligibility_unverified','source_posted_at_utc','source_posted_at_original','content_schema_version'}
def volatile_keys(job):
    # relative text such as Workday 'Posted 3 Days Ago' changes every day without the posting changing
    return {'source_posted_at'} if job.get('timestamp_semantics')=='relative_text_not_a_date' else set()
def changed_fields(previous,job):
    skip=NON_CHANGE_KEYS|volatile_keys(job)
    return sorted(k for k,v in job.items() if k not in skip and previous.get(k)!=v and not (ats_schema_upgrade(previous,job) and k=='description'))
def fingerprint(job):
    job={k:v for k,v in job.items() if k not in volatile_keys(job)}
    return hashlib.sha256(json.dumps(job,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def lever_description(j):
    # Lever keeps requirements/responsibilities in lists, outside company intro.
    sections=[]
    for plain,html in [('openingPlain','opening'),('descriptionBodyPlain','descriptionBody')]:
        v=j.get(plain) or j.get(html)
        if v: sections.append(v)
    if not sections:
        v=j.get('descriptionPlain') or j.get('description')
        if v: sections.append(v)
    lists=j.get('lists',[])
    if not isinstance(lists,list): raise ValueError('Lever lists schema drift')
    for item in lists:
        if not isinstance(item,dict) or not isinstance(item.get('content',''),str):
            raise ValueError('Lever list item schema drift')
        sections.append((item.get('text','')+'\n'+item.get('content','')).strip())
    additional=j.get('additionalPlain') or j.get('additional')
    if additional: sections.append(additional)
    return '\n\n'.join(sections)

def normalize(source, payload):
    ats=source['ats']
    if ats=='lever':
        if not isinstance(payload,list): raise ValueError('Lever expected list, not a zero result')
        jobs=payload
    else:
        if not isinstance(payload,dict) or not isinstance(payload.get('jobs'),list): raise ValueError('Expected jobs array, schema drift not zero')
        jobs=payload['jobs']
    normalized=[]
    for j in jobs:
        if not isinstance(j,dict) or j.get('id') is None: raise ValueError('Job missing stable id')
        title=j.get('title') if ats!='lever' else j.get('text')
        if not title: raise ValueError('Job missing title')
        if ats=='greenhouse':
            loc=j.get('location',{}).get('name',''); description=j.get('content',''); url=j.get('absolute_url'); posted=None; updated=j.get('updated_at'); dtype='updated_at_is_not_posted_at'
        elif ats=='ashby':
            loc=j.get('location',''); description=j.get('descriptionPlain') or j.get('descriptionHtml',''); url=j.get('jobUrl'); posted=j.get('publishedAt'); updated=None; dtype='publishedAt'
            extras=[x.get('location','') for x in j.get('secondaryLocations',[]) if isinstance(x,dict)];loc='; '.join([loc]+extras)
        else:
            loc=j.get('categories',{}).get('location','');description=lever_description(j);url=j.get('hostedUrl'); posted=j.get('createdAt');updated=None;dtype='createdAt_epoch_ms'
        if not url or not url.startswith('https://'): raise ValueError('Missing authoritative job link')
        ireland=irish_location(loc)
        remote_uncertain=remote_ireland_pending(loc, ireland)
        normalized.append({'key':f"{ats}:{source['token']}:{j['id']}",'company':source['company'],'ats':ats,'id':str(j['id']),'title':title,'location':loc,'irish_location_match':ireland,'remote_ireland_eligibility_unverified':bool(remote_uncertain),'context_candidate':bool(LANES.search(title+' '+description)),'job_url':url,'apply_url':j.get('applyUrl'),'source_posted_at':posted,'source_posted_at_utc':posted_utc(posted,dtype),'source_posted_at_original':posted,'source_updated_at':updated,'timestamp_semantics':dtype,'employment_type':j.get('employmentType') or j.get('commitment'),'description':description,'review_state':'NOT_REVIEWED','source_url':source['url'],**({'content_schema_version':2} if ats=='lever' else {})})
    return normalized

def ats_schema_upgrade(previous,job):
    return job.get('ats')=='lever' and previous.get('content_schema_version',1)<job.get('content_schema_version',1)

def pagination_evidence(payload):
    # A valid jobs array is not proof that the provider returned every page.
    if isinstance(payload,dict):
        more=payload.get('hasMore',payload.get('has_more'))
        next_page=payload.get('nextPage',payload.get('next_page',payload.get('nextCursor')))
        if more is True or next_page: return 'INCOMPLETE'
        if more is False: return 'COMPLETE_EXPLICIT'
    return 'NOT_VERIFIED'

def receipt_fields(source, sid, now, previous):
    return {'checked_at':now,'source_url':source['url'],
            'http_status':None,'response_verified':False,'postings_fetched':None,
            'new_raw_count':None,'qualified_count':None,
            'qualification_state':'NOT_ASSESSED','pagination_state':'NOT_VERIFIED',
            'failure_reason':'','failure_streak':previous.get('failure_streak',0)}

def ingest(sources, destination, fetcher=None):
    dest=pathlib.Path(destination);dest.mkdir(parents=True,exist_ok=True)
    p=dest/'state.json';old=json.loads(p.read_text()) if p.exists() else {'jobs':{},'sources':{}}
    state=json.loads(json.dumps(old));health=[];changes=[];fresh_sources=set();now=datetime.now(timezone.utc).isoformat()
    for source in sources:
        sid=source['ats']+':'+source['token'];start=time.monotonic()
        previous_source=old['sources'].get(sid,{})
        receipt=receipt_fields(source,sid,now,previous_source)
        retry_at=previous_source.get('next_attempt_at')
        if not fetcher and retry_at and now<retry_at:
            health.append(receipt|{'source':sid,'status':'BACKOFF','next_attempt_at':retry_at,'last_success_at':previous_source.get('last_success_at'),'failure_reason':previous_source.get('error','Backoff active')});continue
        try:
            if fetcher: payload=fetcher(source)
            else:
                req=urllib.request.Request(source['url'],headers={'Accept':'application/json','User-Agent':'PersonalJobFeedResearch/0.1'})
                with urllib.request.urlopen(req,timeout=20) as r:
                    receipt['http_status']=r.getcode();payload=json.load(r)
                receipt['response_verified']=True
            receipt['pagination_state']=pagination_evidence(payload)
            raw=payload if isinstance(payload,list) else payload.get('jobs') if isinstance(payload,dict) else None
            if isinstance(raw,list): receipt['postings_fetched']=len(raw)
            if receipt['pagination_state']=='INCOMPLETE': raise ValueError('Incomplete pagination: further page indicated; prior baseline retained')
            jobs=normalize(source,payload);seen=set();fresh_sources.add(sid)
            _enrich=globals().get('desc_enricher')
            if _enrich:
                _en,_ef,_es=_enrich(jobs,state)
                receipt['desc_enriched']=_en;receipt['desc_fetch_failed']=_ef
            receipt.update(postings_fetched=len(jobs),new_raw_count=0,failure_streak=0)
            for job in jobs:
                key=job['key'];seen.add(key);h=fingerprint(job);previous=old['jobs'].get(key)
                record=job|{'hash':h,'first_seen_at':previous['first_seen_at'] if previous else now,'last_seen_at':now,'last_check_at':now,'source_status':'OK','stale':False,'active':True}
                state['jobs'][key]=record
                if not previous:
                    changes.append({'key':key,'kind':'NEW','at':now});receipt['new_raw_count']+=1
                elif changed_fields(previous,job): changes.append({'key':key,'kind':'CHANGED','at':now,'fields':changed_fields(previous,job)})
                elif ats_schema_upgrade(previous,job): changes.append({'key':key,'kind':'CONTENT_SCHEMA_BASELINE','at':now})
                elif not previous.get('active',True): changes.append({'key':key,'kind':'REAPPEARED','at':now})
            for key,previous in old['jobs'].items():
                if key.startswith(sid+':') and key not in seen and previous.get('active',True):state['jobs'][key]['active']=False;changes.append({'key':key,'kind':'REMOVED_FROM_FEED','at':now})
            status='OK_NONEMPTY' if jobs else 'OK_ZERO'
            health.append(receipt|{'source':sid,'status':status,'total':len(jobs),'irish':sum(j['irish_location_match'] for j in jobs),'seconds':round(time.monotonic()-start,3),'last_success_at':now})
            state['sources'][sid]={'last_success_at':now,'status':status,'failure_streak':0}
        except Exception as e:
            # Preserve prior data and last success. Errors never mark jobs closed or zero.
            for key,record in state['jobs'].items():
                if key.startswith(sid+':'): record.update(stale=True,source_status='ERROR',last_check_at=now)
            receipt.update(failure_reason=str(e),failure_streak=previous_source.get('failure_streak',0)+1)
            if isinstance(e,urllib.error.HTTPError): receipt['http_status']=e.code
            state['sources'][sid]=previous_source|{'failure_streak':receipt['failure_streak'],'status':'ERROR','last_attempt_at':now,'error':str(e),'next_attempt_at':datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+retry_delay(e),timezone.utc).isoformat()}
            health.append(receipt|{'source':sid,'status':'ERROR','error':str(e),'last_success_at':previous_source.get('last_success_at'),'seconds':round(time.monotonic()-start,3)})
    state['checked_at']=now
    active=[j for j in state['jobs'].values() if j['active'] and j['irish_location_match']]
    summary={'checked_at':now,'source_health':health,'new_count':sum(c['kind']=='NEW' for c in changes),'changes_count':sum(c['kind']!='CONTENT_SCHEMA_BASELINE' for c in changes),'schema_baseline_count':sum(c['kind']=='CONTENT_SCHEMA_BASELINE' for c in changes),'irish_active_raw':len(active),'remote_location_pending':sum(j['active'] and j.get('remote_ireland_eligibility_unverified',False) for j in state['jobs'].values()),'context_candidates_unreviewed':sum(j['context_candidate'] for j in active),'standing_feed':False,'coverage':str(len(sources))+' explicit employer boards only. No whole-board/global coverage claim.'}
    summary.update(source_receipt_schema_version=2,
                   degraded_sources=[h['source'] for h in health if h['status'] in ['ERROR','BACKOFF']],
                   pagination_unverified_sources=[h['source'] for h in health if h['pagination_state']=='NOT_VERIFIED'],
                   qualification_state='NOT_ASSESSED',qualified_count=None)
    # The atomic state file is the recovery authority, including bounded journal and health.
    prior_events=old.get('journal',[])
    if not prior_events and (dest/'changes.jsonl').exists():
        prior_events=[json.loads(line) for line in (dest/'changes.jsonl').read_text().splitlines() if line]
    state['journal']=(prior_events+changes)[-5000:]
    state['source_health']=health
    state['summary']=summary
    for name,value in [('state.json',state),('raw-irish-queue.json',active),('health.json',summary),('last-changes.json',changes)]:
        tmp=dest/(name+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(dest/name)
    tmp=dest/'changes.jsonl.tmp';tmp.write_text('\n'.join(json.dumps(c) for c in state['journal'])+'\n');tmp.replace(dest/'changes.jsonl')
    return summary

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--sources',default='sources.json');a.add_argument('--output',default='output');args=a.parse_args();print(json.dumps(ingest(json.loads(pathlib.Path(args.sources).read_text()),args.output),indent=2))
