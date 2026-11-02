import copy
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import ingest
import ats_extra
import desc_fetch

LONG = 'A' * 6100 + ' No visa sponsorship is available.'

class DescriptionsTest(unittest.TestCase):
    def job(self):
        return dict(key='smartrecruiters:test:1', ats='smartrecruiters', title='Analyst', job_url='https://jobs.smartrecruiters.com/test/1', irish_location_match=True, description='', description_state='MISSING')
    def fetch(self, url):
        return 200, {'jobAd': {'sections': {'requirements': {'text': LONG}}}}
    def run_fetch(self, j, state, now=100000, **kw):
        return desc_fetch.enrich_missing_descriptions([j], state, sleep_s=0, fetcher=kw.pop('fetcher',self.fetch), now_fn=lambda: now, **kw)
    def test_core_feed_retains_full_restriction(self):
        for ats,payload in [('greenhouse',{'jobs':[{'id':1,'title':'Analyst','content':LONG,'location':{'name':'Dublin'},'absolute_url':'https://example.com/1'}]}),('lever',[{'id':1,'text':'Analyst','categories':{'location':'Dublin'},'hostedUrl':'https://example.com/1','descriptionPlain':LONG}]),('ashby',{'jobs':[{'id':1,'title':'Analyst','location':'Dublin','jobUrl':'https://example.com/1','descriptionPlain':LONG}]})]:
            j=ingest.normalize({'ats':ats,'token':'test','company':'test','url':'https://example.com'},payload)[0]
            self.assertIn('No visa sponsorship',j['description']); self.assertGreater(len(j['description']),6000)
    def test_extra_feed_retains_full_description(self):
        j=ats_extra.normalize(dict(ats='recruitee',token='test',company='test',url='https://example.com'),dict(offers=[dict(id=1,title='Analyst',location='Dublin',careers_url='https://example.com/1',description=LONG)]))[0]
        self.assertEqual(j['description'].strip(),LONG)
    def test_detail_not_clipped_and_state_fixed(self):
        j=self.job();s={};self.assertEqual(self.run_fetch(j,s),(1,0,0));self.assertEqual(j['description'],LONG);self.assertEqual(j['description_state'],'PRESENT')
    def seed(self):
        j=self.job();s={};self.run_fetch(j,s);s['jobs']={j['key']:copy.deepcopy(j)};return s
    def test_fresh_cache_reused_without_network(self):
        s=self.seed();j=self.job();self.assertEqual(self.run_fetch(j,s,fetcher=lambda u: self.fail('fresh cache fetched')),(0,0,1));self.assertEqual(j['description'],LONG)
    def test_expired_cache_refetched(self):
        s=self.seed();j=self.job();self.assertEqual(self.run_fetch(j,s,now=100000+86401),(1,0,0))
    def test_title_update_invalidates_cache(self):
        s=self.seed();j=self.job();j['title']='Senior Analyst';self.assertEqual(self.run_fetch(j,s),(1,0,0))
    def test_source_update_invalidates_cache(self):
        s=self.seed();j=self.job();j['source_updated_at']='2026-11-02';self.assertEqual(self.run_fetch(j,s),(1,0,0))
    def test_legacy_cache_is_not_fresh(self):
        j=self.job();s={'jobs':{j['key']:{'description':'old4000'}},'desc_fetch':{j['key']:{'state':'ok'}}};self.assertEqual(self.run_fetch(j,s),(1,0,0));self.assertEqual(j['description'],LONG)
    def test_refresh_failure_keeps_stale_text(self):
        s=self.seed();j=self.job()
        def bad(u):raise urllib.error.HTTPError(u,503,'unavailable',{},None)
        self.assertEqual(self.run_fetch(j,s,now=200000,fetcher=bad),(0,1,0));self.assertEqual(j['description'],LONG);self.assertEqual(j['description_freshness'],'STALE_CACHE')
        self.assertEqual(self.run_fetch(self.job(),s,now=200001,fetcher=bad),(0,0,1))
    def test_old_404_is_retried(self):
        j=self.job();s={'desc_fetch':{j['key']:{'state':'http_404'}}};self.assertEqual(self.run_fetch(j,s),(1,0,0))
    def test_budget_deferral_is_explicit(self):
        j=self.job();self.assertEqual(self.run_fetch(j,{},max_per_run=0),(0,0,1));self.assertEqual(j['description_freshness'],'NOT_FETCHED')
    def test_cache_metadata_does_not_make_content_change(self):
        a=self.job()|dict(description_checked_at='old',description_freshness='FRESH_DETAIL')
        b=self.job()|dict(description_checked_at='new',description_freshness='FRESH_CACHE')
        self.assertEqual(ingest.changed_fields(a,b),[])
    def test_empty_enrichment_context_is_updated(self):
        j=self.job();j['title']='Assistant';j['context_candidate']=False
        with patch('desc_fetch.enrich_missing_descriptions') as f:
            def enrich(jobs,*a,**kw):jobs[0]['description']='Business operations';return 1,0,0
            f.side_effect=enrich;ats_extra._desc_enrich([j],{})
        self.assertEqual(j['description_state'],'PRESENT');self.assertTrue(j['context_candidate'])

if __name__ == '__main__':unittest.main()
