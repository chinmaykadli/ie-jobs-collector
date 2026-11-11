import unittest
import desc_fetch as D
class Provenance(unittest.TestCase):
 def job(self):return {'key':'smartrecruiters:test:1','ats':'smartrecruiters','job_url':'https://jobs.smartrecruiters.com/test/1','irish_location_match':True,'title':'Analyst','description':''}
 def test_cached_not_live_and_ttl_revalidation_edit(self):
  state={'jobs':{}};j=self.job()
  def fetch(u):return 200,{'jobAd':{'sections':{'jobDescription':{'text':'Original full description'}}}}
  D.enrich_missing_descriptions([j],state,sleep_s=0,fetcher=fetch,now_fn=lambda:100000)
  self.assertEqual(j['description_state'],'PRESENT');state['jobs'][j['key']]=j
  cached=self.job();D.enrich_missing_descriptions([cached],state,sleep_s=0,fetcher=lambda _:self.fail('Cache must be used before TTL'),now_fn=lambda:100001)
  self.assertEqual(cached['description_state'],'CACHED');self.assertEqual(cached['description_freshness'],'FRESH_CACHE')
  edited=self.job();D.enrich_missing_descriptions([edited],state,sleep_s=0,fetcher=lambda u:(200,{'jobAd':{'sections':{'x':{'text':'Edited text despite unchanged list'}}}}),now_fn=lambda:100000+D.SUCCESS_TTL+1)
  self.assertEqual(edited['description'],'Edited text despite unchanged list');self.assertEqual(edited['description_state'],'PRESENT')
 def test_bad_status_huge_text_and_failed_refresh_not_present(self):
  for response in [(500,{}),(200,{'jobAd':{'sections':{'x':{'text':'x'*(2*1024*1024+1)}}}})]:
   j=self.job();s={'jobs':{}};a,b,c=D.enrich_missing_descriptions([j],s,sleep_s=0,fetcher=lambda _:response);self.assertEqual(b,1);self.assertNotEqual(j.get('description_state'),'PRESENT')
if __name__=='__main__':unittest.main()
