import unittest,tempfile,pathlib,json,os,threading,base64,urllib.request,urllib.error,time
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import generation_runner as G,candidate_cli as C,ingest
from test_sqlite_parity import S,payload
from test_review1824 import P,HASH
from private_reader import handler
class Review(unittest.TestCase):
 def test_malformed_readonly_noncurrent_quarantined(self):
  for bad in [{},[],{'seq':'2'},{'seq':2}]:
   with self.subTest(bad=bad),tempfile.TemporaryDirectory()as d:
    G.run(d,[S],ingest.ingest,lambda _:payload([1]));root=pathlib.Path(d);p=root/'generations'/'bad';p.mkdir();(p/'manifest.json').write_text(json.dumps(bad));p.chmod(0o555)
    G.run(d,[S],ingest.ingest,lambda _:payload([1,2]));self.assertFalse(p.exists());self.assertEqual(len(list((root/'quarantine').iterdir())),1);G.verify_generation(G.current(d))
 def test_aware_timestamp(self):
  self.assertIsNone(G.aware_timestamp('2026-06-01T12:00:00'));self.assertEqual(G.aware_timestamp('2026-06-01T12:00:00+01:00'),G.aware_timestamp('2026-06-01T11:00:00Z'))
 def test_ingest_nondict_commits(self):
  def other(s,stage,fetcher=None):ingest.ingest(s,stage,fetcher);return None
  with tempfile.TemporaryDirectory()as d:
   with patch.object(ingest,'ingest',other):pass
   result=G.run(d,[S],other,lambda _:payload([1]));self.assertEqual(result['publication_state'],'COMMITTED');self.assertEqual(result['ingest_result_type'],'NoneType')
 def test_unknown_commit_state(self):
  with tempfile.TemporaryDirectory()as d,patch.object(C,'current',side_effect=OSError('unreadable')):
   result=C.collect(d,[S]);self.assertEqual(result['publication_may_have_committed'],'UNKNOWN')
 def test_relative_recovery_current(self):
  from recover_store import inspect,recover
  with tempfile.TemporaryDirectory(dir='.')as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]));self.assertTrue(inspect(d)[0]['current']);name=G.current(d).name;recover(d,name);self.assertEqual(G.current(d).stat().st_mode&0o777,0o555)
 def test_source_error_projection_retains_previous_observation(self):
  with tempfile.TemporaryDirectory()as d:
   G.run(d,[S],ingest.ingest,lambda _:payload([1]),policy=P)
   before=json.loads((G.current(d)/'display.json').read_text());last=before['sources']['greenhouse:fixture']['last_success_at']
   def fail(_):raise TimeoutError('fixture timeout')
   G.run(d,[S],ingest.ingest,fail,policy=P);after=json.loads((G.current(d)/'display.json').read_text());j=after['jobs'][0];self.assertEqual(j['source_status'],'ERROR');self.assertTrue(j['listing_stale']);self.assertEqual(j['source_last_success_at'],last)
 def test_naive_future_reader_refuses(self):
  for stamp in ['2026-06-01T12:00:00','2099-06-01T12:00:00+00:00']:
   with self.subTest(stamp=stamp),tempfile.TemporaryDirectory()as d:
    def modified(s,stage,fetcher=None):
     result=ingest.ingest(s,stage,fetcher);p=stage/'health.json';h=json.loads(p.read_text());h['checked_at']=stamp;p.write_text(json.dumps(h));return result
    G.run(d,[S],modified,lambda _:payload([1]),policy=P)
    server=ThreadingHTTPServer(('127.0.0.1',0),handler(d,'fixture:synthetic',HASH));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
     req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/jobs',headers={'Authorization':'Basic '+base64.b64encode(b'fixture:synthetic').decode()})
     with self.assertRaises(urllib.error.HTTPError)as cm:urllib.request.urlopen(req)
     self.assertEqual(cm.exception.code,503)
    finally:server.shutdown();server.server_close();t.join()
 def test_agency_child_sitemap_incomplete_and_ignored_url_count(self):
  from agency_cycle import crawl
  source={'domain':'example.invalid','sitemaps':['https://example.invalid/sitemap.xml']}
  for kind,entry in [('sitemapindex','sitemap'),('urlset','url')]:
   _,h=crawl(source,lambda _:'<'+kind+'><'+entry+'><loc>https://cdn.invalid/jobs/one</loc></'+entry+'></'+kind+'>');self.assertEqual(h['complete'],kind=='urlset')
   if kind=='urlset':self.assertEqual(h['off_domain_urls'],1)
 def test_sidebar_and_selfclosing_not_job_location(self):
  from agency_safe import parse_page
  text='<div id="post-1" class="job type-job"><h1 class="entry-title">Role</h1><div class="entry-content">Description</div></div><aside><span class="loc">Location: Ireland</span></aside>'
  self.assertFalse(parse_page('redchairrecruitment.ie','https://redchairrecruitment.ie/job/1/',text)['irish_location_match'])
  text=text.replace('<div class="entry-content">','<span class="loc"/><div class="entry-content">');self.assertFalse(parse_page('redchairrecruitment.ie','https://redchairrecruitment.ie/job/1/',text)['irish_location_match'])
 def test_countryless_dublin_not_sufficient(self):
  from agency_safe import parse_page
  for loc in ['Dublin','Dublin, Georgia','Dublin, PA']:
   r={'@type':'JobPosting','title':'Role','description':'Description','jobLocation':{'address':{'addressLocality':loc}}};text='<script type="application/ld+json">'+json.dumps(r)+'</script>'
   self.assertFalse(parse_page('example.invalid','https://example.invalid/job/1',text)['irish_location_match'])
if __name__=='__main__':unittest.main()
