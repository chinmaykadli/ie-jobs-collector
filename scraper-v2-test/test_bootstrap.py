import tempfile,unittest,subprocess,sys,json
from generation_runner import run,current,verify_generation
from test_sqlite_parity import S,payload
import ingest
class Bootstrap(unittest.TestCase):
 def test_initial_crash_before_pointer_recovers_without_lost_state(self):
  with tempfile.TemporaryDirectory()as d:
   code="from test_sqlite_parity import S,payload;import ingest,os,signal,sys;from generation_runner import run;run(sys.argv[1],[S],ingest.ingest,lambda _:payload([1,2]),lambda p:os.kill(os.getpid(),signal.SIGKILL)if p=='before_pointer_swap'else None)"
   p=subprocess.run([sys.executable,'-c',code,d],capture_output=True);self.assertEqual(p.returncode,-9)
   run(d,[S],ingest.ingest,lambda _:payload([1,2,3]));c=current(d);verify_generation(c);self.assertEqual(json.loads((c/'manifest.json').read_text())['seq'],2);self.assertEqual(len(json.loads((c/'state.json').read_text())['jobs']),3)
 def test_post_commit_error_is_explicit_and_never_a_rollback(self):
  from generation_runner import PostCommitError
  with tempfile.TemporaryDirectory()as d:
   def fail(p):
    if p=='after_pointer_swap':raise OSError('injected after commit')
   with self.assertRaises(PostCommitError)as cm:run(d,[S],ingest.ingest,lambda _:payload([1]),fail)
   self.assertTrue(cm.exception.committed);self.assertEqual(cm.exception.generation,current(d).name);verify_generation(current(d))
 def test_kill_during_prune_never_leaves_partial_generation_in_history(self):
  import os,pathlib
  for point in ['before_prune_rename','after_prune_rename','after_prune_delete']:
   with self.subTest(point=point),tempfile.TemporaryDirectory()as d:
    for n in range(1,5):run(d,[S],ingest.ingest,lambda _:payload(list(range(1,n+1))))
    code="from test_sqlite_parity import S,payload;import ingest,os,signal,sys;from generation_runner import run;run(sys.argv[1],[S],ingest.ingest,lambda _:payload([1,2,3,4,5]),lambda p:os.kill(os.getpid(),signal.SIGKILL)if p==sys.argv[2]else None)"
    p=subprocess.run([sys.executable,'-c',code,d,point],capture_output=True);self.assertEqual(p.returncode,-9)
    for generation in (pathlib.Path(d)/'generations').iterdir():verify_generation(generation)
    run(d,[S],ingest.ingest,lambda _:payload([1,2,3,4,5,6]));verify_generation(current(d))
if __name__=='__main__':unittest.main()
