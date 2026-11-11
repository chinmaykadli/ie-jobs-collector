import tempfile, unittest, pathlib, json, sqlite3, sys
from datetime import datetime, timezone
from unittest.mock import patch
import ingest, ats_extra
from sqlite_bridge import install
from sqlite_state import StateTrial
original=install(ingest)
S={'ats':'greenhouse','token':'fixture','company':'Fixture','url':'https://example.invalid/jobs'}
class FixedDate(datetime):
 @classmethod
 def now(cls,tz=None): return cls(2026,11,10,7,0,0,tzinfo=timezone.utc)
def payload(ids):
 return {'jobs':[{'id':i,'title':'Operations Analyst','content':'Business operations and project reporting. '*120,'location':{'name':'Dublin'},'absolute_url':'https://example.invalid/jobs/'+str(i)}for i in ids]}
def clean(s):
 s=json.loads(json.dumps(s))
 if not isinstance(s,dict):return s
 for row in s.get('source_health',[]): row.pop('seconds',None)
 if 'summary'in s:
  for row in s['summary'].get('source_health',[]): row.pop('seconds',None)
 return s
class SQLiteParity(unittest.TestCase):
 def test_three_cycles_match_json_collector(self):
  with tempfile.TemporaryDirectory()as d:
   a=pathlib.Path(d)/'json';b=pathlib.Path(d)/'sqlite'
   with patch.object(ingest,'datetime',FixedDate):
    for p in [payload([1,2]),payload([1,2]),payload([1])]:
     original([S],a,fetcher=lambda s:p);ingest.ingest([S],b,fetcher=lambda s:p)
     self.assertEqual(clean(json.loads((a/'state.json').read_text())),clean(json.loads((b/'state.json').read_text())))
    self.assertEqual(json.loads((b/'last-changes.json').read_text())[0]['kind'],'REMOVED_FROM_FEED')
 def test_error_retains_prior_and_matches(self):
  with tempfile.TemporaryDirectory()as d:
   a=pathlib.Path(d)/'json';b=pathlib.Path(d)/'sqlite'
   with patch.object(ingest,'datetime',FixedDate):
    for fn,out in [(original,a),(ingest.ingest,b)]: fn([S],out,fetcher=lambda s:payload([1,2]))
    def bad(s):raise ValueError('Provider incomplete')
    original([S],a,fetcher=bad);ingest.ingest([S],b,fetcher=bad)
    self.assertEqual(clean(json.loads((a/'state.json').read_text())),clean(json.loads((b/'state.json').read_text())))
    jobs=json.loads((b/'state.json').read_text())['jobs']
    self.assertTrue(all(j['active']and j['stale']for j in jobs.values()))
 def test_abort_preserves_original_database(self):
  with tempfile.TemporaryDirectory()as d:
   ingest.ingest([S],d,fetcher=lambda s:payload([1]))
   p=pathlib.Path(d)/'state.sqlite';before=p.read_bytes()
   with self.assertRaises(RuntimeError):
    with StateTrial(p)as t:
     t.state['jobs']['greenhouse:fixture:1']['active']=False
     raise RuntimeError('simulate interrupted cycle')
   self.assertEqual(before,p.read_bytes());self.assertFalse(p.with_suffix('.working.sqlite').exists())
 def test_working_file_refuses_ambiguous_resume(self):
  with tempfile.TemporaryDirectory()as d:
   ingest.ingest([S],d,fetcher=lambda s:payload([1]));p=pathlib.Path(d)/'state.sqlite';p.with_suffix('.working.sqlite').touch()
   with self.assertRaises(FileExistsError):StateTrial(p)
if __name__=='__main__':unittest.main()
