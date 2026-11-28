"""Public supplemental discovery. GET only, no accounts or qualification decisions.
Bounded landing-page/sitemap coverage, never a whole-Ireland coverage claim.
Run --test for offline regression checks, or --output out for collection.
"""
import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import pathlib
import re
import time
import unittest
import urllib.parse as U
import urllib.request as R
import urllib.robotparser
import xml.etree.ElementTree as ET

UA = 'PersonalJobFeedResearch/0.1'
ATLAS = 'https://www.jobs.atlascopcogroup.com'
WF = 'https://workfinder.ie'
SOURCES = [
    ('atlas-successfactors', ATLAS + '/sitemap.xml', 'successfactors'),
    ('workfinder-business-development', WF + '/other-jobs/business-development', 'workfinder'),
] + [('workfinder-' + name, WF + '/find/country,IE/category,' + number, 'workfinder')
     for name, number in [('sales','93'), ('management','98'), ('engineering','74'),
                          ('customer-service','79'), ('administration','96'), ('logistics','104')]]
IRELAND_PATH = re.compile(r'/job/(?:Dublin|Cork|Galway|Limerick|Waterford|Shannon|Athlone|Ireland)(?:-|%2C)', re.I)
ITEM = re.compile(r'/[^?#]*_i[0-9]+$')
LANES = re.compile(r'\b(sales|business|commercial|operations?|project|program\w*|coordinat\w*|analyst|procurement|supply|customer|account|technical support|process|planning|strategy|graduate)\b', re.I)

class Page(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.links=[]; self.text=[]; self.depth=0; self.desc=[]; self.capture=0; self.titles=[]; self.title_capture=False
        self.feed(raw)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.depth+=1
        if tag=='a' and a.get('href'): self.links.append(a['href'])
        if a.get('itemprop')=='description': self.capture=1
        elif self.capture: self.capture+=1
        if a.get('itemprop')=='title': self.title_capture=True
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.depth=max(0,self.depth-1)
        if self.capture: self.capture-=1
        if tag in ('h1','span') and self.title_capture: self.title_capture=False
    def handle_data(self, text):
        if not self.depth:
            self.text.append(text)
            if self.capture: self.desc.append(text)
            if self.title_capture: self.titles.append(text)

def tidy(parts): return re.sub(r'\s+',' ',' '.join(parts)).strip()
def discover(raw, source_url, provider):
    if provider=='successfactors':
        root=ET.fromstring(raw)
        if not root.tag.endswith('urlset'): raise ValueError('Expected terminal sitemap urlset, not a pagination proof')
        allurls=[e.text for e in root.iter() if e.tag.endswith('loc') and e.text]
        if not allurls: raise ValueError('Empty sitemap is not a verified zero')
        urls=[u for u in allurls if U.urlparse(u).netloc==U.urlparse(source_url).netloc and IRELAND_PATH.search(u)]
        return sorted(set(urls)), {'sitemap_rows':len(allurls),'scope':'BOUNDED_IRISH_CITY_URLS_NOT_GLOBAL_REMOTE','pagination_state':'COMPLETE_WITHIN_SITEMAP_CITY_RULE'}
    page=Page(raw)
    urls={U.urljoin(source_url,u) for u in page.links if ITEM.search(U.urlparse(U.urljoin(source_url,u)).path)}
    urls={u for u in urls if U.urlparse(u).netloc=='workfinder.ie'}
    if not urls: raise ValueError('No item links: blocked/schema drift, not zero jobs')
    return sorted(urls), {'scope':'FIRST_LANDING_PAGE_ONLY_NO_DATE_FILTER','pagination_state':'BOUNDED_NOT_COMPLETE','discovered_links':len(urls)}

def parse_job(raw, url, provider):
    p=Page(raw); text=tidy(p.text); desc=tidy(p.desc)
    if provider=='successfactors':
        title=tidy(p.titles)
        if not title or not desc: raise ValueError('Missing employer title or description')
        m=re.search(r'Your job location (.*?)(?:Why it is great|Application process|Uniting curious)',desc,re.I)
        location=m.group(1).strip() if m else 'Ireland city-path match, exact location needs review'
        return dict(title=title,description=desc,location=location,company='Atlas Copco Group',publisher_posted_at=None,timestamp_semantics='ORIGINAL_POSTING_DATE_NOT_EXPOSED',canonical_status='EMPLOYER_PAGE_REQUIRES_LIVE_APPLY_VERIFICATION')
    m=re.search(r'Published\s+(\d{4}-\d{2}-\d{2})',text)
    if not m: raise ValueError('Missing publisher-date marker: blocked/schema drift')
    # Workfinder dates/pay/remote labels are publisher claims, never employer proof.
    title=text.split(' Post a Resume',1)[0]
    return dict(title=title,description=text,location='Ireland publisher listing, employer location needs review',company='UNRESOLVED_FROM_PUBLISHER',publisher_posted_at=m.group(1),timestamp_semantics='AGGREGATOR_PUBLISHED_DATE_NOT_ORIGINAL',canonical_status='AGGREGATOR_ONLY_EMPLOYER_VERIFICATION_REQUIRED')

class Client:
    def __init__(self): self.robots={}
    def get(self,url):
        origin=U.urlsplit(url); base=origin.scheme+'://'+origin.netloc
        if base not in self.robots:
            rp=urllib.robotparser.RobotFileParser(base+'/robots.txt')
            try:
                with R.urlopen(R.Request(base+'/robots.txt',headers={'User-Agent':UA}),timeout=20) as r: rp.parse(r.read(100000).decode().splitlines())
            except Exception as e: raise ValueError('Robots unavailable, deferred: '+str(e))
            self.robots[base]=rp
        if not self.robots[base].can_fetch(UA,url): raise ValueError('Robots disallows this path')
        time.sleep(1)
        with R.urlopen(R.Request(url,headers={'User-Agent':UA}),timeout=20) as r:
            raw=r.read(4000000)
            if len(raw)==4000000: raise ValueError('Response exceeds safe bound')
            return raw.decode('utf-8','replace'),r.status

def run(destination):
    out=pathlib.Path(destination);out.mkdir(parents=True,exist_ok=True)
    statepath=out/'state.json'
    mainstate=json.loads(statepath.read_text()) if statepath.exists() else {}
    jobs=mainstate.get('supplemental_jobs',{}); receipts=[]; client=Client(); now=dt.datetime.now(dt.timezone.utc).isoformat(); attempted=0
    for sid,url,provider in SOURCES:
        receipt=dict(source=sid,source_url=url,checked_at=now,qualification_state='NOT_ASSESSED')
        try:
            raw,status=client.get(url); links,proof=discover(raw,url,provider); receipt.update(proof,http_status=status,discovered=len(links),status='OK_BOUNDED',details_fetched=0,detail_failures=[])
            # No title prefilter: all discovered rows remain pending, including old rows.
            for link in links:
                previous=jobs.get(link,{})
                job=previous or dict(job_url=link,first_seen_at=now,provider=provider,source=sid,review_state='NOT_REVIEWED',canonical_status='DETAIL_PENDING')
                job['last_seen_at']=now; jobs[link]=job
                age=(dt.datetime.fromisoformat(now)-dt.datetime.fromisoformat(job.get('detail_checked_at',now))).total_seconds()
                if job.get('description') and age<86400: continue
                if attempted>=50: continue
                attempted+=1
                try:
                    detail,_=client.get(link); parsed=parse_job(detail,link,provider)
                    job.update(parsed,detail_checked_at=now,description_freshness='LIVE_PUBLIC_GET',context_candidate=bool(LANES.search(parsed['title']+' '+parsed['description'])))
                    receipt['details_fetched']+=1
                except Exception as e:
                    job['last_error']=str(e);job['description_freshness']='STALE_CACHE' if job.get('description') else 'MISSING';receipt['detail_failures'].append({'url':link,'error':str(e)})
            if receipt['detail_failures']: receipt['status']='DEGRADED_PARTIAL'
        except Exception as e: receipt.update(status='ERROR',error=str(e))
        receipts.append(receipt)
    # Bounded pages cannot prove closure. Retain earlier discoveries for review.
    queue=sorted(jobs.values(),key=lambda j:(bool(j.get('description')),j['first_seen_at']),reverse=True)
    health=dict(checked_at=now,source_health=receipts,raw_discoveries=len(queue),qualified_count=None,qualification_state='NOT_ASSESSED',coverage='8 bounded public sources; not complete Ireland coverage; no automatic closure; detail budget50/run; successful cache24h; failures retried next hourly run',pending_details=sum(not j.get('description') for j in queue))
    mainstate['supplemental_jobs']=jobs
    statepath.write_text(json.dumps(mainstate,ensure_ascii=False))
    hp=out/'health.json'
    mainhealth=json.loads(hp.read_text()) if hp.exists() else {}
    mainhealth['supplemental_discovery']=health
    hp.write_text(json.dumps(mainhealth,ensure_ascii=False,indent=1))
    qp=out/'raw-irish-queue.json'
    # Main employer queue is deliberately not relabelled by aggregator discovery.
    # Separate review-required collection avoids mixing publisher leads into verified employer records.
    mainhealth['supplemental_discovery']['queue']=queue
    hp.write_text(json.dumps(mainhealth,ensure_ascii=False,indent=1))
    print(json.dumps({k:v for k,v in health.items() if k!='queue'},indent=2))

class Tests(unittest.TestCase):
    def test_sitemap(self):
        x='<urlset><url><loc>'+ATLAS+'/job/Dublin-Business/123/</loc></url><url><loc>'+ATLAS+'/job/Belfast-Analyst/456/</loc></url></urlset>'
        urls,p=discover(x,ATLAS+'/sitemap.xml','successfactors'); self.assertEqual(len(urls),1);self.assertIn('Dublin',urls[0])
    def test_empty_is_error(self):
        with self.assertRaises(ValueError): discover('<html>blocked</html>',WF,'workfinder')
    def test_old_workfinder_is_retained(self):
        urls,p=discover('<a href="/business/2026-11-atlas_i4281150334">role</a>',WF,'workfinder');self.assertEqual(len(urls),1);self.assertEqual(p['pagination_state'],'BOUNDED_NOT_COMPLETE')
    def test_date_not_original(self):
        j=parse_job('<title>Sales role</title><p>Published 2026-11-06</p>',WF,'workfinder');self.assertEqual(j['publisher_posted_at'],'2026-11-06');self.assertIn('NOT_ORIGINAL',j['timestamp_semantics'])
    def test_full_employer_text(self):
        text='long responsibility '*1000
        j=parse_job('<h1 itemprop="title">Business development</h1><div itemprop="description">'+text+'</div>',ATLAS,'successfactors');self.assertGreater(len(j['description']),6000)
    def test_no_silent_zero(self):
        with self.assertRaises(ValueError):parse_job('<h1>Denied</h1>',ATLAS,'successfactors')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--test',action='store_true');a.add_argument('--output',default='out'); args=a.parse_args()
    if args.test: unittest.main(argv=['supplemental_discovery.py'],exit=True)
    else:run(args.output)
