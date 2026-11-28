"""Bounded public agency discovery. GET-only, no accounts or applications.
All sitemap job URLs are retained before ranking. No slug-based rejection.
Raw/pending/verified-fit are distinct. Bounded sitemaps cannot prove closure.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import html
import json
import pathlib
import re
import time
import unittest
import urllib.parse as U
import xml.etree.ElementTree as ET
import ingest as I
from supplemental_discovery import Client, Page, tidy

JOBRE = re.compile(r'/(jobs?|vacanc\w*|job-details?|positions?)/[^/?#]+', re.I)
SKIP = re.compile(r'/discipline/|/jobs/(sector|specialism|in-)|/(jobs?|vacancies)/(contract|permanent|temporary|city|send-us|local-jobs|job-roles|[a-z-]+-jobs/?$)', re.I)
LANES = re.compile(r'\b(sales|support|graduate|trainee|apprentice|operations?|project|program\w*|analyst|business|commercial|account|customer|coordinat\w*|supply|procurement|planning|strategy|implementation|process|quality|partnership|revenue)\b',re.I)

def job_url(url): return bool(JOBRE.search(U.urlparse(url).path) and not SKIP.search(U.urlparse(url).path))
def title_slug(url): return re.sub(r'[-_]+',' ',U.unquote(U.urlparse(url).path.rstrip('/').rsplit('/',1)[-1]))
def same_site(url,domain):
    host=U.urlparse(url).hostname or ''
    return host==domain or host.endswith('.'+domain)
def sitemap_links(raw):
    root=ET.fromstring(raw)
    if not root.tag.endswith(('sitemapindex','urlset')): raise ValueError('Not a sitemap, cannot count as zero')
    return root.tag.endswith('sitemapindex'),[e.text.strip() for e in root.iter() if e.tag.endswith('loc') and e.text]

def crawl(source):
    client=Client(); queue=list(source['sitemaps']);visited=set();found=set();errors=[];responses=[];deadline=time.monotonic()+75
    while queue and len(visited)<4 and time.monotonic()<deadline:
        url=queue.pop(0)
        if url in visited or not same_site(url,source['domain']):continue
        visited.add(url)
        try:
            raw,code=client.get(url);index,links=sitemap_links(raw);responses.append({'url':url,'http_status':code,'entries':len(links)})
            if index:
                # Job maps first, but do not reject other sitemap children permanently.
                children=[u for u in links if same_site(u,source['domain'])]
                queue=sorted(children,key=lambda u:not bool(re.search('job|vacanc|position',u,re.I)))+queue
            else:
                found.update(u for u in links if same_site(u,source['domain']) and job_url(u))
        except Exception as e:errors.append({'url':url,'error':str(e)})
    status='DEGRADED_PARTIAL' if errors else 'OK_BOUNDED'
    if not found: status='ERROR' if errors else 'NO_JOB_URLS_UNVERIFIED'
    return source['domain'],sorted(found),dict(source=source['domain'],source_urls=source['sitemaps'],status=status,urls_discovered=len(found),responses=responses,errors=errors,sitemap_backlog=len(queue),coverage='BOUNDED_MAX4_SITEMAPS_75SECONDS_NOT_COMPLETE')

def postings(value):
    if isinstance(value,list):
        for v in value:yield from postings(v)
    elif isinstance(value,dict):
        kind=value.get('@type');kind=kind if isinstance(kind,list) else [kind]
        if 'JobPosting' in kind:yield value
        if '@graph' in value:yield from postings(value['@graph'])

def parse_detail(raw,url):
    p=Page(raw);text=tidy(p.text);data=None
    for match in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',raw,re.S|re.I):
        try:data=next(postings(json.loads(match)),None)
        except (ValueError,TypeError):continue
        if data:break
    if not data:
        # No location inferred from site headers/footers. Full page retained for review.
        m=re.search(r'<h1[^>]*>(.*?)</h1>',raw,re.S|re.I)
        if not m or len(text)<200 or re.search(r'access denied|verify you are human|just a moment',text[:300],re.I):raise ValueError('No credible job detail, blocked/schema drift')
        title=tidy(Page(m.group(1)).text)
        if title.lower() in ('job description','job details','vacancy'):
            titles=re.search(r'<title[^>]*>(.*?)</title>',raw,re.S|re.I)
            title=tidy(Page(titles.group(1)).text) if titles else title_slug(url)
        return dict(title=title,description=text,location='',location_review_state='LOCATION_UNRESOLVED',context_candidate=bool(LANES.search(title+' '+text)),employer='UNRESOLVED_AGENCY_CLIENT',posted_at=None)
    title=html.unescape(data.get('title') or '')
    desc=tidy(Page(html.unescape(data.get('description') or '')).text)
    if not title or not desc:raise ValueError('JobPosting lacks title/description')
    locs=data.get('jobLocation') or [];locs=locs if isinstance(locs,list) else [locs];locations=[]
    for loc in locs:
        if not isinstance(loc,dict):continue
        a=loc.get('address') or {}
        if not isinstance(a,dict):continue
        country=a.get('addressCountry') or ''
        if isinstance(country,dict):country=country.get('name') or country.get('identifier') or ''
        locations.append(', '.join(str(a.get(k)) for k in ['addressLocality','addressRegion'] if a.get(k))+(', '+country if country else ''))
    location='; '.join(locations).strip(', ')
    irish=I.irish_location(location) or bool(re.search(r'(?:^|[,; ])IE(?:$|[,; ])',location))
    # Unknown, remote and foreign-looking rows remain retained for review, never auto-excluded.
    ls='IRISH_LOCATION_CLAIM_REQUIRES_REVIEW' if irish else 'LOCATION_UNRESOLVED_OR_NON_IRISH_REVIEW'
    org=data.get('hiringOrganization') or {}; employer=org.get('name') if isinstance(org,dict) else None
    return dict(title=title,description=desc,location=location,location_review_state=ls,context_candidate=bool(LANES.search(title+' '+desc)),employer=employer or 'UNRESOLVED_AGENCY_CLIENT',posted_at=data.get('datePosted'))

def eligible_for_detail(job,now):
    checked=job.get('detail_checked_at')
    return not checked or (dt.datetime.fromisoformat(now)-dt.datetime.fromisoformat(checked)).total_seconds()>=86400

def select_details(jobs,now,cap):
    pending=[j for j in jobs if eligible_for_detail(j,now) and (not j.get('next_attempt_at') or j['next_attempt_at']<=now)]
    # Oldest-attempt first ensures generic/nonlane URLs and old legacy skipped records get read.
    # Lane words break ties only, never eliminate candidates.
    return sorted(pending,key=lambda j:(j.get('last_attempt_at',''),not bool(LANES.search(title_slug(j['job_url']))),j.get('first_seen_at',''),j['job_url']))[:cap]

def run(destination,sources=None,cap=40,crawler=crawl,detail_fetch=None):
    out=pathlib.Path(destination);out.mkdir(parents=True,exist_ok=True);sp=out/'state.json'
    state=json.loads(sp.read_text()) if sp.exists() else {};jobs=state.get('agency_jobs',{});now=dt.datetime.now(dt.timezone.utc).isoformat()
    legacy_path=pathlib.Path('state/agency-seen.json');legacy=json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
    sources=sources if sources is not None else json.loads(pathlib.Path('agency_sources.json').read_text())
    receipts=[]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        for domain,urls,receipt in pool.map(crawler,sources):
            receipt.update(checked_at=now,qualification_state='NOT_ASSESSED');receipts.append(receipt)
            for url in urls:
                prior=legacy.get(url,{})
                jobs.setdefault(url,dict(key='agency:'+domain+':'+url,job_url=url,agency=domain,first_seen_at=now,legacy_first_seen_at=prior.get('first_seen'),legacy_skipped_without_detail=prior.get('detail') is False,review_state='NOT_REVIEWED',canonical_status='AGENCY_CLIENT_AND_LIVE_APPLY_VERIFICATION_REQUIRED',description_state='MISSING'))
                jobs[url]['last_seen_at']=now
    # Recover legacy false-detail records even if absent from today's bounded sitemap page.
    domains={s['domain'] for s in sources}
    for url,prior in legacy.items():
        domain=next((d for d in domains if same_site(url,d)),None)
        if domain and prior.get('detail') is False and job_url(url):
            jobs.setdefault(url,dict(key='agency:'+domain+':'+url,job_url=url,agency=domain,first_seen_at=now,legacy_first_seen_at=prior.get('first_seen'),legacy_skipped_without_detail=True,review_state='NOT_REVIEWED',canonical_status='AGENCY_CLIENT_AND_LIVE_APPLY_VERIFICATION_REQUIRED',description_state='MISSING'))
    todo=select_details(list(jobs.values()),now,cap);fetched=failed=0
    # Sequential requests, shared robots cache, one-second client pacing. Bound total time.
    client=Client();deadline=time.monotonic()+150
    for job in todo:
        if time.monotonic()>deadline:break
        job['last_attempt_at']=now
        try:
            raw=detail_fetch(job['job_url']) if detail_fetch else client.get(job['job_url'])[0]
            parsed=parse_detail(raw,job['job_url']);job.update(parsed,detail_checked_at=now,description_state='PRESENT',description_freshness='LIVE_PUBLIC_GET',qualification_state='NOT_ASSESSED');job.pop('next_attempt_at',None);job.pop('last_error',None);fetched+=1
        except Exception as e:
            failed+=1;job.update(last_error=str(e),description_freshness='STALE_CACHE' if job.get('description') else 'MISSING',next_attempt_at=(dt.datetime.fromisoformat(now)+dt.timedelta(hours=6)).isoformat())
    state['agency_jobs']=jobs
    pending=sum(not j.get('description') for j in jobs.values())
    queue=sorted(jobs.values(),key=lambda j:(bool(j.get('description')),bool(j.get('context_candidate')),j['first_seen_at']),reverse=True)
    health=dict(checked_at=now,source_health=receipts,raw_discoveries=len(jobs),details_fetched=fetched,detail_failures=failed,pending_details=pending,legacy_blindspot_recovered=sum(j.get('legacy_skipped_without_detail',False) for j in jobs.values()),qualified_count=None,qualification_state='NOT_ASSESSED',coverage='29 configured agencies; bounded sitemap crawl4pages/source75seconds,4workers; detail40/run150seconds; failures6hbackoff; fulltext; no slug rejection; no closure inference; client/Irishlocation/liveapply/dedupe/visa/pay all require review',queue=queue)
    hp=out/'health.json';h=json.loads(hp.read_text()) if hp.exists() else {};h['agency_discovery']=health
    for path,value in [(sp,state),(hp,h)]:
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False));temp.replace(path)
    print(json.dumps({k:v for k,v in health.items() if k!='queue'},indent=2));return health

class Tests(unittest.TestCase):
    def test_sales_support_grad(self):
        now='2026-11-28T00:00:00+00:00';js=[{'job_url':'https://x.ie/jobs/'+x,'first_seen_at':now} for x in ['sales','support','graduate','123456']]
        self.assertEqual(len(select_details(js,now,40)),4)
    def test_nonlane_eventually_first(self):
        now='2026-11-28T00:00:00+00:00';js=[{'job_url':'https://x.ie/jobs/sales','last_attempt_at':now},{'job_url':'https://x.ie/jobs/12345'}];self.assertIn('12345',select_details(js,now,1)[0]['job_url'])
    def test_jsonld_multiloc_no_truncate(self):
        d={'@type':'JobPosting','title':'Graduate support','description':'Responsibility '*1000,'jobLocation':[{'address':{'addressLocality':'Dublin','addressCountry':'IE'}},{'address':{'addressLocality':'London','addressCountry':'GB'}}]};r=parse_detail('<script type="application/ld+json">'+json.dumps(d)+'</script>','https://x/jobs/1');self.assertGreater(len(r['description']),6000);self.assertIn('Dublin',r['location'])
    def test_footer_not_location(self):
        r=parse_detail('<h1>Sales</h1>'+('text '*100)+'<footer>Dublin Ireland</footer>','https://x/jobs/sales');self.assertEqual(r['location_review_state'],'LOCATION_UNRESOLVED')
    def test_bot_not_zero(self):
        with self.assertRaises(ValueError):sitemap_links('<html>Access denied</html>')
    def test_foreign_never_irish(self):
        d={'@type':'JobPosting','title':'Support','description':'Business Dublin clients','jobLocation':{'address':{'addressLocality':'London','addressCountry':'GB'}}};r=parse_detail('<script type="application/ld+json">'+json.dumps(d)+'</script>','https://x/jobs/1');self.assertNotEqual(r['location_review_state'],'IRISH_LOCATION_CLAIM_REQUIRES_REVIEW')
    def test_path_language_not_blanket_excluded(self):self.assertTrue(job_url('https://x.ie/en-us/jobs/sales-graduate'))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--test',action='store_true');a.add_argument('--output',default='out');args=a.parse_args()
    if args.test:unittest.main(argv=['agency_feed.py'])
    else:run(args.output)
