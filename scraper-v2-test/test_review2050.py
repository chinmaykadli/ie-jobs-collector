import unittest,tempfile,pathlib,json,io
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import ingest,candidate_cli as C,bounded_http as B,generation_runner as G
from test_sqlite_parity import S,payload
class Clock(datetime):
 current=datetime(2026,11,10,12,tzinfo=timezone.utc)
 @classmethod
 def now(cls,tz=None):return cls.current
class Resp(io.BytesIO):
 def getcode(self):return 200
class Review(unittest.TestCase):
 def test_actual_config_unique_and_invalid_refused(self):
  sources=json.loads(pathlib.Path('sources.json').read_text());self.assertEqual(ingest.validate_sources(sources),135)
  for sources in [[S,S],[dict(S,token='bad:token')],[dict(S,ats='bad:ats')]]:
   with self.assertRaises(ValueError):ingest.validate_sources(sources)
   with tempfile.TemporaryDirectory()as d:
    result=C.collect(d,sources,fetcher=lambda _:payload([1]));self.assertFalse(result['completed']);self.assertFalse((pathlib.Path(d)/'current').exists())
 def test_storage_failure_nonfatal_and_symlinks_ignored(self):
  with tempfile.TemporaryDirectory()as d,tempfile.TemporaryDirectory()as external:
   root=pathlib.Path(d);q=root/'quarantine';q.mkdir();outside=pathlib.Path(external);(outside/'big').write_bytes(b'x'*1000);(q/'link').symlink_to(outside,target_is_directory=True)
   self.assertEqual(C.storage_stats(root)['quarantine']['bytes'],0)
   with patch.object(pathlib.Path,'iterdir',side_effect=PermissionError('test')):self.assertEqual(C.storage_stats(root),{'error':'PermissionError'})
   G.run(d,[S],ingest.ingest,lambda _:payload([1]))
   with patch.object(C.os,'walk',side_effect=FileNotFoundError('raced trim')):
    (root/'abandoned'/'folder').mkdir();result=C.collect(d,[S],fetcher=lambda _:payload([1,2]));self.assertTrue(result['completed']);self.assertEqual(result['storage'],{'error':'FileNotFoundError'})
   self.assertTrue((root/'ops.jsonl').read_text())
 def test_live_transport_backoff_and_two_zero_windows(self):
  # fetcher=None is intentional: exercise real production branch, patch only HTTP.
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'datetime',Clock),patch.object(ingest,'desc_enricher',None):
   Clock.current=datetime(2026,11,10,12,tzinfo=timezone.utc)
   def live(body):return patch.object(B,'urlopen',lambda *a,**k:Resp(json.dumps(body).encode()))
   with live(payload([1,2])):ingest.ingest([S],d)
   def state():return json.loads((pathlib.Path(d)/'state.json').read_text())
   first=state();last=first['sources']['greenhouse:fixture']['last_success_at']
   with patch.object(B,'urlopen',side_effect=TimeoutError('test')):h=ingest.ingest([S],d)
   self.assertEqual(h['source_health'][0]['status'],'ERROR')
   with patch.object(B,'urlopen',side_effect=AssertionError('must not fetch during backoff')):h=ingest.ingest([S],d)
   self.assertEqual(h['source_health'][0]['status'],'BACKOFF');self.assertEqual(state()['sources']['greenhouse:fixture']['last_success_at'],last);self.assertTrue(all(r['stale']and r['active']for r in state()['jobs'].values()))
   Clock.current+=timedelta(hours=2)
   with live(payload([])):h=ingest.ingest([S],d)
   self.assertEqual(h['source_health'][0]['status'],'ERROR');self.assertIn('SUSPECT_ZERO_OR_DROP',h['source_health'][0]['failure_reason']);self.assertTrue(all(r['active']for r in state()['jobs'].values()))
   with patch.object(B,'urlopen',side_effect=AssertionError('must back off suspect zero')):h=ingest.ingest([S],d)
   self.assertEqual(h['source_health'][0]['status'],'BACKOFF');self.assertEqual(state()['sources']['greenhouse:fixture']['last_success_at'],last)
   Clock.current+=timedelta(hours=2)
   with live(payload([])):h=ingest.ingest([S],d)
   self.assertEqual(h['source_health'][0]['status'],'OK_ZERO');self.assertTrue(all(not r['active']for r in state()['jobs'].values()))
if __name__=='__main__':unittest.main()
