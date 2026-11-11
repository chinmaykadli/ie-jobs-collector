import unittest,tempfile,pathlib,json
from unittest.mock import patch
import ingest,ats_extra,candidate_cli as C,sqlite_state
from sqlite_bridge import install
from test_sqlite_parity import S,payload,original
from test_review2050 import Review
from tests.test_workday_quarantine import S as W,job,payload as wp
class Review2200(unittest.TestCase):
 def test_backoff_and_validation_both_stores_explicit(self):
  install(ingest);sql=ingest.ingest
  for fn,store in [(original,'json'),(sql,'sqlite')]:
   with self.subTest(store=store),patch.object(ingest,'ingest',fn):
    Review().test_actual_config_unique_and_invalid_refused();Review().test_live_transport_backoff_and_two_zero_windows()
 def test_candidate_disables_enrichment(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',lambda *a:(_ for _ in()).throw(AssertionError('detail path'))):
   self.assertTrue(C.collect(d,[S],fetcher=lambda _:payload([1]))['completed']);self.assertTrue((C.current(d)/'state.sqlite').exists())
 def test_workday_collision_quarantines_both_and_protects_baseline(self):
  for fn in [original,ingest.ingest]:
   with tempfile.TemporaryDirectory()as d:
    fn([W],d,fetcher=lambda _:wp([job('1'),job('2')]))
    a,b=job('1'),job('1');b['externalPath']='/job/AnotherPosting_1';h=fn([W],d,fetcher=lambda _:wp([a,b]));self.assertEqual(h['source_health'][0]['status'],'DEGRADED_PARTIAL');self.assertEqual(h['source_health'][0]['total'],0)
    st=json.loads((pathlib.Path(d)/'state.json').read_text());self.assertTrue(all(r['active']for r in st['jobs'].values()));self.assertEqual(json.loads((pathlib.Path(d)/'last-changes.json').read_text()),[])
 def test_mid_source_error_rolls_back_json_and_sqlite(self):
  for fn in [original,ingest.ingest]:
   with tempfile.TemporaryDirectory()as d:
    fn([S],d,fetcher=lambda _:payload([1,2]));before=json.loads((pathlib.Path(d)/'state.json').read_text())
    orig=ingest.fingerprint
    def failsecond(j):
     if j['id']=='4':raise RuntimeError('mid-source')
     return orig(j)
    with patch.object(ingest,'fingerprint',failsecond):h=fn([S],d,fetcher=lambda _:payload([3,4]))
    after=json.loads((pathlib.Path(d)/'state.json').read_text());self.assertEqual(set(before['jobs']),set(after['jobs']));self.assertTrue(all(r['active']and r['stale']for r in after['jobs'].values()));self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertEqual(json.loads((pathlib.Path(d)/'last-changes.json').read_text()),[])
 def test_late_source_failure_rolls_back_and_keeps_multisource_order(self):
  t=dict(S,token='second')
  for fn in [original,ingest.ingest]:
   with tempfile.TemporaryDirectory()as d:
    fn([S,t],d,fetcher=lambda _:payload([1,2]));before=json.loads((pathlib.Path(d)/'state.json').read_text());orig=ingest.time.monotonic;n=[0]
    def clock():
     n[0]+=1
     if n[0]==2:raise RuntimeError('after writes before health')
     return orig()
    with patch.object(ingest.time,'monotonic',clock):h=fn([S],d,fetcher=lambda _:payload([3]))
    after=json.loads((pathlib.Path(d)/'state.json').read_text());self.assertEqual(list(before['jobs']),list(after['jobs']));self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertEqual(json.loads((pathlib.Path(d)/'last-changes.json').read_text()),[])
 def test_low_overlap_confirmation_and_scope_event(self):
  for fn in [original,ingest.ingest]:
   with tempfile.TemporaryDirectory()as d:
    fn([S],d,fetcher=lambda _:payload(range(10)));h=fn([S],d,fetcher=lambda _:payload(range(10,20)));self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertEqual(len(json.loads((pathlib.Path(d)/'state.json').read_text())['jobs']),10);h=fn([S],d,fetcher=lambda _:payload(range(10,20)));self.assertEqual(h['source_health'][0]['status'],'OK_NONEMPTY')
   with tempfile.TemporaryDirectory()as d:
    fn([W],d,fetcher=lambda _:wp([job('1'),job('2')]));fn([W],d,fetcher=lambda _:wp([job('1')]));self.assertEqual(json.loads((pathlib.Path(d)/'last-changes.json').read_text())[0]['kind'],'REMOVED_FROM_SEARCH_SCOPE')
 def test_empty_ids_unknown_provider_and_missing_workday_total(self):
  with self.assertRaises(ValueError):ingest.validate_sources([dict(S,ats='unknown')])
  for fn in [original,ingest.ingest]:
   with tempfile.TemporaryDirectory()as d:
    p=payload([1]);p['jobs'][0]['id']='';h=fn([S],d,fetcher=lambda _:p);self.assertEqual(h['source_health'][0]['status'],'ERROR')
if __name__=='__main__':unittest.main()

class HealthTailRegression(unittest.TestCase):
 def test_release_failure_has_one_error_health_and_rolls_back(self):
  with tempfile.TemporaryDirectory() as d:
   ingest.ingest([S],d,fetcher=lambda _:payload([1,2]))
   p=pathlib.Path(d)/'state.sqlite'
   with sqlite_state.StateTrial(p) as trial:
    real=trial.db
    class FailReleaseOnce:
     failed=False
     def __getattr__(self,name):return getattr(real,name)
     def execute(self,sql,*args):
      if sql=='RELEASE source_jobs' and not self.failed:
       self.failed=True
       raise RuntimeError('injected release failure')
      return real.execute(sql,*args)
    trial.db=FailReleaseOnce()
    h=original([S],d,fetcher=lambda _:payload([3]),state_trial=trial)
    self.assertEqual(len(h['source_health']),1)
    self.assertEqual(h['source_health'][0]['status'],'ERROR')
    self.assertEqual(h['degraded_sources'],['greenhouse:fixture'])
    rows=list(trial.state['jobs'].items())
    self.assertEqual([k for k,v in rows],['greenhouse:fixture:1','greenhouse:fixture:2'])
    self.assertTrue(all(v['active'] and v['stale'] for k,v in rows))
    self.assertEqual(json.loads((pathlib.Path(d)/'last-changes.json').read_text()),[])
    trial.db=real
