import unittest,tempfile,pathlib,json,sqlite3,io
from import_state import Stream,import_state,records
class Tiny(io.StringIO):
 def read(self,n=-1):return super().read(min(3,n)if n>=0 else 3)
class Importer(unittest.TestCase):
 def test_split_numbers_strings_unicode_objects(self):
  for val in [1234567890123,-3.14159,True,None,'a☘𐍈b'*50,{'a':[1,2,3]},{}]:
   p=Stream(Tiny(json.dumps(val,ensure_ascii=False)));self.assertEqual(p.value(),val)
 def test_empty_absent_sections_round_trip_presence(self):
  for val in [{'jobs':{},'sources':{}},{'jobs':{},'sources':{},'desc_fetch':{}}]:
   with tempfile.TemporaryDirectory()as d:
    p=pathlib.Path(d)/'s.json';p.write_text(json.dumps(val));db=p.with_suffix('.sqlite');import_state(p,db)
    with sqlite3.connect(db)as c:self.assertEqual(set(k for k, in c.execute('select key from section_presence')),set(val))
 def test_bad_input_no_database_left(self):
  for text in ['{"jobs":','{"jobs":{},"jobs":{}}junk','{"jobs":{"x":{},"x":{}}}','{"jobs":{}} trailing']:
   with tempfile.TemporaryDirectory()as d:
    p=pathlib.Path(d)/'s.json';p.write_text(text);dest=p.with_suffix('.sqlite')
    with self.assertRaises((ValueError,sqlite3.IntegrityError)):import_state(p,dest)
    self.assertFalse(dest.exists());self.assertFalse(dest.with_suffix('.importing.sqlite').exists())
 def test_oversized_value_refused_without_silent_clip(self):
  p=Stream(io.StringIO(json.dumps('x'*200000)),max_value_chars=131072)
  with self.assertRaisesRegex(ValueError,'safe limit'):p.value()
if __name__=='__main__':unittest.main()
