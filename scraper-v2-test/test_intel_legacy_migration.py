import unittest,tempfile,pathlib,json,copy
from intel_legacy_migration import plan,migrate,digest,TARGET
class MigrationTests(unittest.TestCase):
 def fixture(self,p):
  d={'version':1,'jobs':{TARGET:{'ats':'workday','id':'Spotlight Job','active':True,'description':'original exact text'},'greenhouse:test:1':{'id':'1','active':True}},'sources':{'workday:intel':{'last_success_at':'old'}},'desc_fetch':{},'custom':{'preserve':[1,2]}}
  p.write_text(json.dumps(d));return d
 def test_exact_preservation_and_quarantine(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';d=self.fixture(src);before=src.read_bytes();rep=migrate(src,root/'out',digest(src));o=json.loads((root/'out/state.json').read_text());expected=copy.deepcopy(d);del expected['jobs'][TARGET];self.assertEqual(o,expected);self.assertEqual(src.read_bytes(),before);self.assertEqual(json.loads((root/'out/quarantine.json').read_text())[0]['record'],d['jobs'][TARGET]);self.assertEqual(rep['semantics'],'IDENTITY_QUARANTINE_NOT_JOB_CLOSURE')
 def test_wrong_hash_and_overwrite_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';self.fixture(src)
   with self.assertRaises(ValueError):migrate(src,root/'out','wrong')
   migrate(src,root/'out',digest(src))
   with self.assertRaises(FileExistsError):migrate(src,root/'out',digest(src))
 def test_repeated_migration_no_more_quarantine(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';self.fixture(src);migrate(src,root/'out',digest(src));p=root/'out/state.json';r=migrate(p,root/'again',digest(p));self.assertEqual(r['quarantine'],[]);self.assertEqual(json.loads(p.read_text()),json.loads((root/'again/state.json').read_text()))
 def test_empty_sections_survive(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';src.write_text('{"jobs":{},"sources":{},"desc_fetch":{},"meta":5}');migrate(src,root/'out',digest(src));self.assertEqual(json.loads(src.read_text()),json.loads((root/'out/state.json').read_text()))
 def test_bad_shape_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';src.write_text(json.dumps({'jobs':{TARGET:{'ats':'greenhouse','id':'Spotlight Job'}}}))
   with self.assertRaises(ValueError):plan(src)
 def test_writer_corruption_refused(self):
  from unittest.mock import patch
  import intel_legacy_migration as mod
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';self.fixture(src);original=mod.write_output
   def corrupt(a,b):
    original(a,b);d=json.loads(b.read_text());d['jobs']['greenhouse:test:1']['active']=False;b.write_text(json.dumps(d))
   with patch.object(mod,'write_output',corrupt):
    with self.assertRaises(ValueError):migrate(src,root/'out',digest(src))
   self.assertFalse((root/'out').exists())
 def test_no_replace_race(self):
  import intel_legacy_migration as mod
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);src=root/'in.json';self.fixture(src);original=mod.rename_noreplace
   def race(a,b):b.mkdir();original(a,b)
   with patch.object(mod,'rename_noreplace',race):
    with self.assertRaises(FileExistsError):migrate(src,root/'out',digest(src))
   self.assertEqual(list((root/'out').iterdir()),[])
 def test_plan_does_not_claim_source_unchanged(self):
  with tempfile.TemporaryDirectory() as td:
   src=pathlib.Path(td)/'in.json';self.fixture(src);self.assertEqual(plan(src)['source_unchanged'],'NOT_CHECKED')
if __name__=='__main__':unittest.main()
