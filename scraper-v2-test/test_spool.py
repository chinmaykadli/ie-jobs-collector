import unittest,tempfile,pathlib,json
from unittest.mock import patch
import ingest,ats_extra,bounded_http
class Spool(unittest.TestCase):
 def test_real_collect_path_disk_array(self):
  s={'ats':'lever','token':'fixture','company':'Fixture','url':'https://example.invalid/list'}
  payload=[{'id':'1','text':'Operations Analyst','categories':{'location':'Dublin'},'hostedUrl':'https://example.invalid/job/1','descriptionPlain':'Work description'}]
  def fake(req,path,**kw):path.write_text(json.dumps(payload));return 200,path.stat().st_size
  with tempfile.TemporaryDirectory()as d,patch.object(bounded_http,'download',fake),patch.object(ingest,'desc_enricher',None):
   h=ingest.ingest([s],d);self.assertEqual(h['irish_active_raw'],1);self.assertEqual(h['source_health'][0]['postings_fetched'],1);self.assertEqual(h['source_health'][0]['http_status'],200)
if __name__=='__main__':unittest.main()
