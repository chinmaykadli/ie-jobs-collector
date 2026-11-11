import unittest,tempfile,pathlib,copy,sqlite3
from test_sqlite_parity import S,payload
import ingest
from sqlite_state import StateTrial
class Contract(unittest.TestCase):
 def test_detached_records_require_explicit_assign(self):
  with tempfile.TemporaryDirectory()as d:
   ingest.ingest([S],d,fetcher=lambda _:payload([1]));p=pathlib.Path(d)/'state.sqlite';k='greenhouse:fixture:1'
   with StateTrial(p)as t:
    a=t.state['jobs'][k];a['nested']={'x':[1]};self.assertNotIn('nested',t.state['jobs'][k]);t.state['jobs'][k]=a
    b=copy.deepcopy(t.state['jobs'][k]);b['nested']['x'].append(2);self.assertEqual(t.state['jobs'][k]['nested'],{'x':[1]})
    with self.assertRaises(TypeError):t.state['jobs'].setdefault(k,{})
 def test_explicit_sequence_survives_vacuum(self):
  with tempfile.TemporaryDirectory()as d:
   ingest.ingest([S],d,fetcher=lambda _:payload([3,1,2]));p=pathlib.Path(d)/'state.sqlite'
   with sqlite3.connect(p)as db:before=db.execute('select key from jobs order by seq').fetchall();db.execute('vacuum');self.assertEqual(before,db.execute('select key from jobs order by seq').fetchall())
if __name__=='__main__':unittest.main()
