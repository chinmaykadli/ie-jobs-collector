import copy,json,pathlib,tempfile,unittest
from unittest.mock import patch
import ingest,ats_extra
S={'ats':'workday','token':'accenture','company':'Accenture','url':'https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs'}
def job(i):return {'title':'Operations Analyst','bulletFields':[str(i),'Dublin'],'locationsText':'Dublin, Ireland','externalPath':'/job/Dublin/Analyst_'+str(i)}
def payload(rows):return {'jobs':rows,'complete':True,'total':len(rows)}
class QuarantineTest(unittest.TestCase):
 def run_feed(self,d,rows):
  with patch.object(ingest,'desc_enricher',None):return ingest.ingest([S],d,fetcher=lambda _:payload(rows))
 def test_one_bad_141_valid(self):
  rows=[job(i) for i in range(141)]+[{'bulletFields':['R00313152','Dublin']}]
  v=ats_extra.normalize(S,payload(rows));self.assertEqual(len(v),141);self.assertEqual(v.quarantined_records,[{'id':'R00313152','reason':'Job missing title'}])
  with tempfile.TemporaryDirectory() as d:
   h=self.run_feed(d,rows);r=h['source_health'][0];self.assertEqual(r['status'],'DEGRADED_PARTIAL');self.assertEqual(r['postings_fetched'],142);self.assertEqual(r['valid_postings_count'],141);self.assertEqual(r['quarantined_count'],1);self.assertEqual(h['irish_active_raw'],141);self.assertIn('workday:accenture',h['degraded_sources']);self.assertIsNone(r['last_success_at']);self.assertFalse(h['standing_feed'])
 def test_all_bad_not_ok_zero(self):
  with tempfile.TemporaryDirectory() as d:
   h=self.run_feed(d,[{'bulletFields':['1']}]);self.assertEqual(h['source_health'][0]['status'],'DEGRADED_PARTIAL');self.assertEqual(h['source_health'][0]['total'],0);self.assertIn('workday:accenture',h['degraded_sources'])
 def test_missing_stable_id_remains_error(self):
  with self.assertRaisesRegex(ValueError,'stable id'):ats_extra.normalize(S,payload([{}]))
  with tempfile.TemporaryDirectory() as d:
   h=self.run_feed(d,[{}]);self.assertEqual(h['source_health'][0]['status'],'ERROR')
 def test_withdrawal_protection_and_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   first=self.run_feed(d,[job('1'),job('2'),job('3')]);success=first['source_health'][0]['last_success_at']
   h=self.run_feed(d,[job('1'),{'bulletFields':['2']}]);state=json.loads((pathlib.Path(d)/'state.json').read_text());changes=json.loads((pathlib.Path(d)/'last-changes.json').read_text())
   for i in ['2','3']:
    r=state['jobs']['workday:accenture:'+i];self.assertTrue(r['active']);self.assertTrue(r['stale']);self.assertEqual(r['source_status'],'DEGRADED_PARTIAL')
   self.assertFalse(any(c['kind']=='REMOVED_FROM_FEED' for c in changes));self.assertEqual(h['source_health'][0]['last_success_at'],success)
   h=self.run_feed(d,[job('1')]);self.assertNotIn('workday:accenture',h['degraded_sources']);self.assertEqual(h['source_health'][0]['status'],'OK_NONEMPTY');self.assertEqual(h['irish_active_raw'],1)
 def test_missing_path_quarantined(self):
  j=job('1');del j['externalPath'];v=ats_extra.normalize(S,payload([j]));self.assertEqual(v.quarantined_records[0]['reason'],'Missing authoritative job link')
 def test_other_ats_remains_strict(self):
  with self.assertRaisesRegex(ValueError,'title'):ats_extra.normalize({'ats':'workable','token':'test'}, {'jobs':[{'id':'1','url':'https://example.com'}]})
 def test_all_bad_preserves_prior(self):
  with tempfile.TemporaryDirectory() as d:
   self.run_feed(d,[job('1')]);h=self.run_feed(d,[{'bulletFields':['1']}]);self.assertEqual(h['irish_active_raw'],1);self.assertEqual(h['source_health'][0]['status'],'DEGRADED_PARTIAL')
