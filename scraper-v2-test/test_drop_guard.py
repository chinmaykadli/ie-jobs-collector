import unittest,tempfile,pathlib,json
from unittest.mock import patch
from test_sqlite_parity import S,payload,FixedDate
import ingest
# A separate process/import picks up the bridge's freshly transformed ingest.
class DropGuard(unittest.TestCase):
 def test_zero_requires_two_matching_successes(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   ingest.ingest([S],d,fetcher=lambda _:payload([1,2]));first=ingest.ingest([S],d,fetcher=lambda _:payload([]));self.assertEqual(first['irish_active_raw'],2);self.assertEqual(first['source_health'][0]['status'],'ERROR')
   second=ingest.ingest([S],d,fetcher=lambda _:payload([]));self.assertEqual(second['irish_active_raw'],0)
 def test_mass_drop_requires_matching_repeat_not_different_subset(self):
  with tempfile.TemporaryDirectory()as d,patch.object(ingest,'desc_enricher',None):
   ingest.ingest([S],d,fetcher=lambda _:payload(list(range(20))))
   for ids,expected in [([1],20),([2],20),([2],1)]:self.assertEqual(ingest.ingest([S],d,fetcher=lambda _:payload(ids))['irish_active_raw'],expected)
if __name__=='__main__':unittest.main()
