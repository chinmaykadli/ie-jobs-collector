import unittest,tempfile,pathlib,json,threading,base64,urllib.request,urllib.error,time,ssl,subprocess,sys
from unittest.mock import patch
import ingest,candidate_cli as C,generation_runner as G
from test_sqlite_parity import S,payload
from screen_policy import validate,pinned,load_policy
from private_reader import handler
from http.server import ThreadingHTTPServer
P={'verified':True,'blocked_companies':['NeverUsedFixture']};HASH=validate(P)['sha256']
class Review(unittest.TestCase):
 def test_policy_pin_duplicate_and_rollover_display(self):
  with self.assertRaises(ValueError):load_policy('{"verified":true,"blocked_companies":["Acme"],"blocked_companies":[]}')
  with self.assertRaises(ValueError):pinned(P,'wrong')
  from regenerate_display import regenerate
  with tempfile.TemporaryDirectory()as d:
   C.collect(d,[S],P,lambda _:payload([1]),expected_policy_sha256=HASH);before=G.current(d);old=json.loads((before/'display.json').read_text())
   newp={'verified':True,'blocked_companies':['Fixture']};regenerate(d,newp,validate(newp)['sha256']);new=json.loads((G.current(d)/'display.json').read_text());self.assertEqual(new['jobs'],[]);self.assertEqual(old['feed_as_of'],new['feed_as_of']);self.assertGreater(new['seq'],old['seq'])
 def test_recovery_retains_newer_and_never_reuses_seq(self):
  from recover_store import recover
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]));a=G.current(d)
   G.run(d,[S],ingest.ingest,lambda _:payload([1,2]));b=G.current(d)
   recover(d,a.name);G.run(d,[S],ingest.ingest,lambda _:payload([1,2,3]));c=G.current(d);self.assertEqual(json.loads((c/'manifest.json').read_text())['seq'],3)
   self.assertTrue((pathlib.Path(d)/'superseded'/b.name).exists());G.verify_generation(pathlib.Path(d)/'superseded'/b.name)
 def test_other_run_commit_not_claimed_by_loser(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]),run_id='prior')
   def other(*a,**k):
    G.run(d,[S],ingest.ingest,lambda _:payload([1,2]),run_id='other');raise RuntimeError('Collector already running')
   with patch.object(C,'run',other):result=C.collect(d,[S])
   self.assertFalse(result['publication_may_have_committed']);self.assertTrue(result['pointer_changed'])
 def test_reader_stale_and_external_pin_change(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]),policy=P)
   server=ThreadingHTTPServer(('127.0.0.1',0),handler(d,'fixture:synthetic',HASH,max_age_seconds=-1));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
   try:
    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/jobs',headers={'Authorization':'Basic '+base64.b64encode(b'fixture:synthetic').decode()})
    with urllib.request.urlopen(req)as response:self.assertTrue(json.load(response)['stale'])
   finally:server.shutdown();server.server_close();t.join()
 def test_sitemap_image_locations_are_not_job_urls(self):
  from agency_cycle import crawl
  source={'domain':'example.invalid','sitemaps':['https://example.invalid/sitemap.xml']};text='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"><url><loc>https://example.invalid/jobs/one</loc><image:image><image:loc>https://cdn.invalid/image.jpg</image:loc></image:image></url></urlset>'
  urls,h=crawl(source,lambda _:text);self.assertTrue(h['complete']);self.assertEqual(urls,['https://example.invalid/jobs/one'])
if __name__=='__main__':unittest.main()
