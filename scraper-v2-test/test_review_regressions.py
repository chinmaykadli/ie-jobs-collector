import unittest,json,tempfile,pathlib,threading,urllib.request,urllib.error,base64
from agency_safe import update,parse_page
from screen_policy import validate,company
from private_reader import handler
from http.server import ThreadingHTTPServer
class Review(unittest.TestCase):
 def test_strict_policy_and_name_variants(self):
  for p in [{'verified':'false','blocked_companies':[]},{'verified':True},{'verified':True,'blocked_companies':'Acme'},{'verified':True,'blocked_companies':[],'unknown':1}]:self.assertIsNone(validate(p))
  self.assertEqual(company('A\u200bcme\u00a0 Ltd.'),company('Acme'))
 def test_agency_softfailure_keeps_text_and_failing_urls_do_not_starve(self):
  good=lambda _: '<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Example','description':'Verified full text','jobLocation':{'address':{'addressCountry':'IE'}}})+'</script>'
  s,_=update({},'fixture',['good'],True,good,now=100)
  s,r=update(s,'fixture',['good'],True,lambda _:'<title>Bot wall</title>',now=90000)
  self.assertEqual(s['jobs']['good']['description'],'Verified full text');self.assertEqual(s['jobs']['good']['description_state'],'CACHED');self.assertEqual(r['changes'],[])
  urls=['bad'+str(i)for i in range(200)]+['zzzgood'];s={}
  def fetch(u):
   if u.startswith('bad'):raise ValueError('permanent failure')
   return good(u)
  for n in range(3):s,r=update(s,'fixture',urls,True,fetch,now=100+n,max_details=100)
  self.assertIn('zzzgood',s['jobs']);self.assertEqual(s['jobs']['zzzgood']['description_state'],'PRESENT')
 def test_duplicate_ld_type_none_and_country_only(self):
  r={'@type':'JobPosting','title':'Example','description':'Full text','jobLocation':{'address':{'addressCountry':'IE'}}};ld=json.dumps(r)
  text='<script type></script><script type="application/LD+JSON">'+ld+'</script><script type="application/ld+json">'+ld+'</script>'
  self.assertTrue(parse_page('fixture','https://example.invalid/job',text)['irish_location_match'])
 def test_host_header_rejected_before_prompt(self):
  with tempfile.TemporaryDirectory()as d:
   s=ThreadingHTTPServer(('127.0.0.1',0),handler(d,'fixture:test'));t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
   try:
    req=urllib.request.Request('http://127.0.0.1:'+str(s.server_port),headers={'Host':'evil.invalid'})
    with self.assertRaises(urllib.error.HTTPError)as cm:urllib.request.urlopen(req)
    self.assertEqual(cm.exception.code,400);self.assertIsNone(cm.exception.headers.get('WWW-Authenticate'))
   finally:s.shutdown();s.server_close();t.join()
if __name__=='__main__':unittest.main()
