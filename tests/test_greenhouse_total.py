import json,pathlib,tempfile,unittest
from unittest.mock import patch
import ingest,ats_extra
S={'ats':'greenhouse','company':'Test','token':'test','url':'https://boards-api.greenhouse.io/v1/boards/test/jobs?content=true'}
def job(i):return {'id':i,'title':'Operations Analyst','location':{'name':'Dublin, Ireland'},'absolute_url':'https://example.com/jobs/'+str(i),'content':'Responsibilities and requirements'}
def payload(rows,total):return {'jobs':rows,'meta':{'total':total}}
class GreenhouseTotalTest(unittest.TestCase):
 def test_complete_counts_and_zero(self):
  for rows in ([],[job(1)],[job(1),job('2')]):
   self.assertEqual(ats_extra.pagination_evidence(payload(rows,len(rows)),S),'COMPLETE_EXPLICIT')
 def test_mismatch_duplicate_and_bad_total(self):
  for p in [payload([job(1)],2),payload([job(1),job(2)],1),payload([job(1),job(1)],2),payload([job(1),job('1')],2),payload([job(1)],True),payload([],None),payload([],-1),payload([],'0'),payload([{}],1),payload([job(True)],1)]:
   with self.subTest(p=p):self.assertEqual(ats_extra.pagination_evidence(p,S),'INCOMPLETE')
 def test_explicit_more_wins_over_matching_total(self):
  for extra in ({'hasMore':True},{'nextPage':2},{'nextCursor':'abc'}):
   self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],1)|extra,S),'INCOMPLETE')
 def test_missing_metadata_not_invented(self):
  self.assertEqual(ats_extra.pagination_evidence({'jobs':[job(1)]},S),'NOT_VERIFIED')
  self.assertEqual(ats_extra.pagination_evidence({'jobs':[],'meta':{}},S),'NOT_VERIFIED')
 def test_other_adapters_and_no_source_unchanged(self):
  self.assertEqual(ats_extra.pagination_evidence(payload([],0)),'NOT_VERIFIED')
  self.assertEqual(ats_extra.pagination_evidence(payload([],0),{'ats':'ashby'}),'NOT_VERIFIED')
  self.assertEqual(ats_extra.pagination_evidence({'complete':True}, {'ats':'workday'}),'COMPLETE_EXPLICIT')
  self.assertEqual(ats_extra.pagination_evidence({'totalFound':2,'content':[{},{}]}, {'ats':'smartrecruiters'}),'COMPLETE_EXPLICIT')
 def test_partial_preserves_baseline_then_real_withdrawal(self):
  with tempfile.TemporaryDirectory() as d,patch.object(ingest,'desc_enricher',None):
   def run(p):return ingest.ingest([S],d,fetcher=lambda _:p)
   first=run(payload([job(1),job(2)],2));success=first['source_health'][0]['last_success_at']
   h=run(payload([job(1)],2));state=json.loads((pathlib.Path(d)/'state.json').read_text());changes=json.loads((pathlib.Path(d)/'last-changes.json').read_text())
   self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertEqual(h['source_health'][0]['last_success_at'],success);self.assertEqual(h['irish_active_raw'],2)
   self.assertTrue(state['jobs']['greenhouse:test:2']['active']);self.assertTrue(state['jobs']['greenhouse:test:2']['stale']);self.assertFalse(any(x['kind']=='REMOVED_FROM_FEED' for x in changes))
   h=run(payload([job(1)],1));self.assertEqual(h['irish_active_raw'],1);self.assertEqual(h['source_health'][0]['status'],'OK_NONEMPTY')
   h=run(payload([],0));self.assertEqual(h['source_health'][0]['status'],'OK_ZERO');self.assertEqual(h['irish_active_raw'],0)
