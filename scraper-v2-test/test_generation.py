import unittest,tempfile,pathlib,os,subprocess,sys,json,hashlib,sqlite3
from unittest.mock import patch
from test_sqlite_parity import original,FixedDate,payload,S
import ingest
from generation_runner import run,current,writer
class Generations(unittest.TestCase):
 def test_all_exception_checkpoints_preserve_old_until_swap(self):
  for point in ['before_collect','after_collect','before_generation_rename','before_pointer_swap']:
   with self.subTest(point=point),tempfile.TemporaryDirectory()as d,patch.object(ingest,'datetime',FixedDate):
    run(d,[S],ingest.ingest,lambda _:payload([1]));before=current(d)
    def fail(p):
     if p==point:raise OSError('Simulated disk or write failure')
    with self.assertRaises(OSError):run(d,[S],ingest.ingest,lambda _:payload([1,2]),fail)
    self.assertEqual(current(d),before);self.assertEqual(len(json.loads((before/'state.json').read_text())['jobs']),1)
 def test_swap_is_commit_and_reopen_works(self):
  with tempfile.TemporaryDirectory()as d:
   run(d,[S],ingest.ingest,lambda _:payload([1]));a=current(d)
   run(d,[S],ingest.ingest,lambda _:payload([1,2]));b=current(d)
   self.assertNotEqual(a,b);self.assertEqual(len(json.loads((b/'state.json').read_text())['jobs']),2)
   self.assertTrue((a/'state.sqlite').exists())
 def test_concurrent_process_refused(self):
  with tempfile.TemporaryDirectory()as d,writer(d):
   p=subprocess.run([sys.executable,'-c',"from generation_runner import writer; import sys;\nwith writer(sys.argv[1]):pass",d],capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0);self.assertIn('already running',p.stderr)
 def test_sigkill_at_every_checkpoint_and_restart(self):
  for point in ['before_collect','after_collect','before_generation_rename','before_pointer_swap','after_pointer_swap']:
   with self.subTest(point=point),tempfile.TemporaryDirectory()as d:
    run(d,[S],ingest.ingest,lambda _:payload([1]));old=current(d)
    code="from test_sqlite_parity import S,payload; import ingest,os,signal,sys; from generation_runner import run; run(sys.argv[1],[S],ingest.ingest,lambda _:payload([1,2]),lambda p:os.kill(os.getpid(),signal.SIGKILL) if p==sys.argv[2] else None)"
    p=subprocess.run([sys.executable,'-c',code,d,point],capture_output=True,text=True);self.assertEqual(p.returncode,-9)
    snap=current(d);state=json.loads((snap/'state.json').read_text());self.assertEqual(len(state['jobs']),2 if point=='after_pointer_swap'else 1)
    with sqlite3.connect(snap/'state.sqlite')as db:self.assertEqual(db.execute('pragma integrity_check').fetchone()[0],'ok')
    run(d,[S],ingest.ingest,lambda _:payload([1,2,3]));self.assertEqual(len(json.loads((current(d)/'state.json').read_text())['jobs']),3)
 def test_snapshot_backup_restore(self):
  import shutil
  with tempfile.TemporaryDirectory()as d,tempfile.TemporaryDirectory()as restore:
   run(d,[S],ingest.ingest,lambda _:payload([1,2]));src=current(d);target=pathlib.Path(restore)/'generations'/src.name;target.parent.mkdir();shutil.copytree(src,target);(pathlib.Path(restore)/'current').symlink_to(pathlib.Path('generations')/src.name)
   run(restore,[S],ingest.ingest,lambda _:payload([1,2,3]));self.assertEqual(len(json.loads((current(restore)/'state.json').read_text())['jobs']),3)
if __name__=='__main__':unittest.main()
