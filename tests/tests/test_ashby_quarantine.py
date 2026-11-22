import json,pathlib,tempfile,unittest
from unittest.mock import patch
import ingest,ats_extra
S={'ats':'ashby','company':'Test','token':'test','url':'https://api.ashbyhq.com/posting-api/job-board/test'}
def job(i,title='Operations Analyst'):
 return {'id':i,'title':title,'location':'Dublin, Ireland','descriptionPlain':'Full description.','jobUrl':'https://jobs.ashbyhq.com/test/'+str(i),'publishedAt':'2026-11-22T00:00:00Z'}
class AshbyQuarantineTests(unittest.TestCase):
 def test_healthy_records_unchanged(self):
  records=ingest.normalize(S,{'jobs':[job('1'),job('2')]})
  self.assertEqual(len(records),2);self.assertEqual(records.quarantined_records,[])
  self.assertTrue(all(j['irish_location_match']for j in records))
 def test_blank_or_absent_title_quarantined_with_stable_id(self):
  for title in ('',None):
   records=ingest.normalize(S,{'jobs':[job('1'),job('2',title)]})
   self.assertEqual(len(records),1);self.assertEqual(records.quarantined_records,[{'id':'2','reason':'Job missing title'}])
 def test_missing_identity_still_fails_closed(self):
  for malformed in ({'title':''},dict(job('1'),id=None),None):
   with self.assertRaises(ValueError):ingest.normalize(S,{'jobs':[job('2'),malformed]})
 def test_unknown_title_schema_still_fails_closed(self):
  for title in (17,False,0,[],{}):
   with self.assertRaises((TypeError,ValueError)):ingest.normalize(S,{'jobs':[job('1',title)]})
 def test_other_providers_still_fail_closed(self):
  greenhouse=dict(S,ats='greenhouse')
  with self.assertRaises(ValueError):ingest.normalize(greenhouse,{'jobs':[job('1','')]})
 def test_missing_owning_url_still_fails_closed(self):
  j=job('1');j.pop('jobUrl')
  with self.assertRaises(ValueError):ingest.normalize(S,{'jobs':[j]})
 def test_partial_refresh_keeps_unseen_baseline_and_last_full_success(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   def run(jobs):return ingest.ingest([S],d,fetcher=lambda _: {'jobs':jobs})
   first=run([job('1'),job('2'),job('withdrawn')]);success=first['source_health'][0]['last_success_at']
   current=job('2');current['descriptionPlain']='Updated full description'
   h=run([job('1',''),current,job('new')]);receipt=h['source_health'][0]
   self.assertEqual(receipt['status'],'DEGRADED_PARTIAL');self.assertEqual(receipt['last_success_at'],success)
   self.assertEqual(receipt['quarantined_records'],[{'id':'1','reason':'Job missing title'}]);self.assertEqual(receipt['quarantined_count'],1)
   self.assertEqual(receipt['postings_fetched'],3);self.assertEqual(receipt['valid_postings_count'],2)
   self.assertEqual(h['qualified_count'],None);self.assertEqual(h['qualification_state'],'NOT_ASSESSED');self.assertFalse(h['standing_feed'])
   state=json.loads((pathlib.Path(d)/'state.json').read_text());events=json.loads((pathlib.Path(d)/'last-changes.json').read_text())
   for i in ['1','withdrawn']:
    self.assertTrue(state['jobs']['ashby:test:'+i]['active']);self.assertTrue(state['jobs']['ashby:test:'+i]['stale'])
   self.assertFalse(state['jobs']['ashby:test:2']['stale']);self.assertEqual(state['jobs']['ashby:test:2']['description'],'Updated full description')
   self.assertTrue(state['jobs']['ashby:test:new']['active']);self.assertFalse(any(e['kind']=='REMOVED_FROM_FEED'for e in events))
   h=run([job('2'),job('new')]);self.assertEqual(h['source_health'][0]['status'],'OK_NONEMPTY');self.assertEqual(h['irish_active_raw'],2)
 def test_all_quarantined_is_partial_not_zero(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   h=ingest.ingest([S],d,fetcher=lambda _: {'jobs':[job('1','')]})
   self.assertEqual(h['source_health'][0]['status'],'DEGRADED_PARTIAL');self.assertEqual(h['source_health'][0]['quarantined_count'],1)
 def test_real_empty_response_still_zero(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   h=ingest.ingest([S],d,fetcher=lambda _: {'jobs':[]});self.assertEqual(h['source_health'][0]['status'],'OK_ZERO')
