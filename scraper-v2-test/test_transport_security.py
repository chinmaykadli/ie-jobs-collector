import unittest,io,gzip,tempfile,pathlib
from unittest.mock import patch
import bounded_http as B
class Raw(io.BytesIO):
 def __init__(self,body,status=200,headers=None):super().__init__(body);self.status=status;self.headers=headers or{}
 def getcode(self):return self.status
 def geturl(self):return 'https://example.invalid/jobs'
class Transport(unittest.TestCase):
 def test_nonpublic_and_schemes_rejected(self):
  for u in ['file:///etc/passwd','data:text/plain,a','ftp://example.invalid/x','http://127.0.0.1/x','https://127.0.0.1/x','https://169.254.169.254/x','https://user:pass@example.invalid/x']:
   with self.assertRaises(ValueError):B.check_public(u)
 def test_redirect_identity_and_host(self):
  h=B.RestrictedRedirect();req=B.urllib.request.Request('https://example.invalid/jobs/one')
  with patch.object(B,'check_public',lambda u:B.urlsplit(u)):
   for u in ['https://evil.invalid/jobs/one','https://example.invalid/jobs/two']:
    with self.assertRaises(ValueError):h.redirect_request(req,None,302,'',{},u)
 def test_truncation_partial_gzip_trailing_and_atomic_spool(self):
  cases=[Raw(b'abc',headers={'Content-Length':'8'}),Raw(b'abc',status=206),Raw(gzip.compress(b'abc')+b'trailing',headers={'Content-Encoding':'gzip'})]
  for raw in cases:
   with self.subTest(raw=raw),patch.object(B,'BASE_OPEN',lambda *a,**k:raw):
    with self.assertRaises(ValueError):B.urlopen('https://example.invalid/jobs')
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d)/'body';p.write_text('prior')
   with patch.object(B,'BASE_OPEN',lambda *a,**k:Raw(b'abc',headers={'Content-Length':'8'})):
    with self.assertRaises(ValueError):B.download('https://example.invalid/jobs',p)
   self.assertEqual(p.read_text(),'prior');self.assertFalse(p.with_name('body.tmp').exists())
if __name__=='__main__':unittest.main()
