import unittest,tempfile,pathlib,json
from unittest.mock import patch
import candidate_cli as C,ingest
from generation_runner import run,current,verify_generation
from test_sqlite_parity import S,payload
from sqlite_bridge import install
class Operations(unittest.TestCase):
 def test_entrypoint_reports_failure_and_preserves_generation(self):
  install(ingest)
  with tempfile.TemporaryDirectory()as d:
   result=C.collect(d,[S],fetcher=lambda _:payload([1]));self.assertTrue(result['completed']);old=current(d)
   with patch.object(C,'run',side_effect=KeyboardInterrupt()):
    with self.assertRaises(KeyboardInterrupt):C.collect(d,[S])
   self.assertEqual(current(d),old)
 def test_restore_explicit_generation_and_restart(self):
  from recover_store import recover,inspect
  install(ingest)
  with tempfile.TemporaryDirectory()as d:
   run(d,[S],ingest.ingest,lambda _:payload([1]));a=current(d)
   run(d,[S],ingest.ingest,lambda _:payload([1,2]));b=current(d);(pathlib.Path(d)/'current').unlink()
   self.assertEqual(len(inspect(d)),2);recover(d,b.name);self.assertEqual(current(d),b)
   run(d,[S],ingest.ingest,lambda _:payload([1,2,3]));verify_generation(current(d))
if __name__=='__main__':unittest.main()
