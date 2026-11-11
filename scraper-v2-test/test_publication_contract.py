import unittest,tempfile,pathlib,json,os,errno
from unittest.mock import patch
from test_sqlite_parity import S,payload
import ingest
import generation_runner as G
class Publication(unittest.TestCase):
 def test_dangling_or_deleted_current_fails_closed(self):
  with tempfile.TemporaryDirectory()as d:
   root=pathlib.Path(d);(root/'generations').mkdir();(root/'current').symlink_to('generations/missing')
   with self.assertRaises(FileNotFoundError):G.current(root)
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]));G.run(d,[S],ingest.ingest,lambda _:payload([1,2]));(pathlib.Path(d)/'current').unlink()
   with self.assertRaisesRegex(ValueError,'Missing current'):G.run(d,[S],ingest.ingest,lambda _:payload([1,2]))
 def test_read_does_not_block_collection(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]))
   with G.reader(d)as old:
    G.run(d,[S],ingest.ingest,lambda _:payload([1,2]));self.assertTrue((old/'state.json').exists());self.assertNotEqual(old,G.current(d))
 def test_manifest_extra_missing_corruption_refused(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]));old=G.current(d);p=old/'health.json';p.chmod(0o600);p.write_text('{}')
   with self.assertRaisesRegex(ValueError,'integrity'):G.run(d,[S],ingest.ingest,lambda _:payload([1,2]))
 def test_enospc_and_eio_fsync_keep_old(self):
  for code in [errno.ENOSPC,errno.EIO,errno.EROFS]:
   with self.subTest(errno=code),tempfile.TemporaryDirectory()as d:
    G.run(d,[S],ingest.ingest,lambda _:payload([1]));old=G.current(d)
    with patch.object(G,'syncfile',side_effect=OSError(code,'Injected filesystem failure')):
     with self.assertRaises(OSError):G.run(d,[S],ingest.ingest,lambda _:payload([1,2]))
    self.assertEqual(old,G.current(d));G.verify_generation(old)
 def test_projection_without_policy_is_empty_and_no_private_fields(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]));p=json.loads((G.current(d)/'display.json').read_text());self.assertEqual(p['jobs'],[]);self.assertFalse(p['policy_available'])
   G.run(d,[S],ingest.ingest,lambda _:payload([1]),policy={'verified':True,'blocked_companies':['Fixture']});self.assertEqual(json.loads((G.current(d)/'display.json').read_text())['jobs'],[])
if __name__=='__main__':unittest.main()
