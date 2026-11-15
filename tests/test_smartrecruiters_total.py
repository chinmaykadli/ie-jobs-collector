import json,pathlib,tempfile,unittest
from unittest.mock import patch
import ingest,ats_extra
S={'ats':'smartrecruiters','company':'Test','token':'test','url':'https://api.smartrecruiters.com/v1/companies/test/postings?country=ie&limit=100'}
def job(i):return {'id':i,'name':'Operations Analyst','location':{'city':'Dublin','country':'ie'},'releasedDate':'2026-11-15T00:00:00Z'}
def payload(rows,total,offset=0):return {'content':rows,'totalFound':total,'offset':offset,'limit':100}
class SmartRecruitersTotalTest(unittest.TestCase):
 def test_valid_integer_and_documented_string_counts(self):
  for n in (0,1,2):
   for string in (False,True):
    self.assertEqual(ats_extra.pagination_evidence(payload([job(str(i))for i in range(n)],str(n)if string else n,'0'if string else 0),S),'COMPLETE_EXPLICIT')
 def test_missing_total_is_not_complete(self):
  self.assertEqual(ats_extra.pagination_evidence({'content':[],'offset':0},S),'NOT_VERIFIED')
 def test_bad_totals(self):
  for total in (True,None,-1,1.0,'-1','1.0','',{},[]):
   with self.subTest(total=total):self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],total),S),'INCOMPLETE')
 def test_offset_must_be_zero(self):
  for offset in (None,True,-1,1,'1',0.0):
   self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],1,offset),S),'INCOMPLETE')
 def test_duplicate_and_missing_ids(self):
  for rows in ([job(1),job(1)],[job(1),job('1')],[{}],[job(True)],[job('')],[job(' ')],[None]):
   self.assertEqual(ats_extra.pagination_evidence(payload(rows,len(rows)),S),'INCOMPLETE')
 def test_count_mismatch_both_directions(self):
  for total in (0,2):self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],total),S),'INCOMPLETE')
 def test_continuation_signals_win(self):
  for extra in ({'hasMore':True},{'has_more':True},{'nextPage':2},{'next_page':'next'},{'nextCursor':'x'}):
   self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],1)|extra,S),'INCOMPLETE')
 def test_false_complete_cannot_override_bad_count(self):
  self.assertEqual(ats_extra.pagination_evidence(payload([job(1)],2)|{'complete':True},S),'INCOMPLETE')
 def test_non_list_content_fails_closed(self):
  self.assertEqual(ats_extra.pagination_evidence({'totalFound':0,'offset':0,'content':{}},S),'INCOMPLETE')
 def test_other_adapters_unchanged(self):
  self.assertEqual(ats_extra.pagination_evidence({'complete':True},{'ats':'workday'}),'COMPLETE_EXPLICIT')
  self.assertEqual(ats_extra.pagination_evidence({'totalFound':2,'content':[{},{}]}),'COMPLETE_EXPLICIT')
 def test_duplicate_page_keeps_baseline_and_true_withdrawal_works(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   def run(p):return ingest.ingest([S],d,fetcher=lambda _:p)
   h=run(payload([job(1),job(2)],2));success=h['source_health'][0]['last_success_at']
   for bad in (payload([job(1),job(1)],2),payload([job(1)],0),payload([job(1)],1,1)):
    h=run(bad);state=json.loads((pathlib.Path(d)/'state.json').read_text());changes=json.loads((pathlib.Path(d)/'last-changes.json').read_text())
    self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertEqual(h['source_health'][0]['last_success_at'],success);self.assertEqual(h['irish_active_raw'],2)
    self.assertTrue(state['jobs']['smartrecruiters:test:2']['active']);self.assertTrue(state['jobs']['smartrecruiters:test:2']['stale']);self.assertFalse(any(x['kind']=='REMOVED_FROM_FEED'for x in changes))
   h=run(payload([job(1)],1));self.assertEqual(h['irish_active_raw'],1)
   h=run(payload([],0));self.assertEqual(h['source_health'][0]['status'],'OK_ZERO');self.assertEqual(h['irish_active_raw'],0)
