import unittest,threading,time,gzip,json
from http.server import HTTPServer,BaseHTTPRequestHandler
from bounded_http import urlopen
from unittest.mock import patch
import urllib.request,bounded_http
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  route=self.path
  if route=='/429':self.send_response(429);self.send_header('Retry-After','7200');self.end_headers();return
  data=gzip.compress(b'x'*200000)if route=='/gzip'else(b'{"jobs":[]}'if route=='/json'else b'x'*200000)
  self.send_response(200)
  if route=='/gzip':self.send_header('Content-Encoding','gzip')
  self.end_headers()
  try:
   if route=='/drip':
    for _ in range(30):self.wfile.write(b'x');self.wfile.flush();time.sleep(.025)
   else:self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError):pass
class HTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.s=HTTPServer(('127.0.0.1',0),Handler);cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.t.start();cls.base='http://127.0.0.1:'+str(cls.s.server_port);cls.override=patch.object(bounded_http,'BASE_OPEN',urllib.request.urlopen);cls.override.start()
 @classmethod
 def tearDownClass(cls):cls.override.stop();cls.s.shutdown();cls.s.server_close();cls.t.join()
 def test_json(self):
  with urlopen(self.base+'/json')as r:self.assertEqual(json.load(r),{'jobs':[]})
 def test_429_not_retried(self):
  from urllib.error import HTTPError
  with self.assertRaises(HTTPError)as cm:urlopen(self.base+'/429')
  self.assertEqual(cm.exception.headers['Retry-After'],'7200')
 def test_wire_limit(self):
  with self.assertRaisesRegex(ValueError,'byte limit'):urlopen(self.base+'/large',max_bytes=10000)
 def test_gzip_bomb_cap(self):
  with self.assertRaisesRegex(ValueError,'byte limit'):urlopen(self.base+'/gzip',max_bytes=10000)
 def test_slow_drip_deadline(self):
  start=time.monotonic()
  with self.assertRaises(TimeoutError):urlopen(self.base+'/drip',total_seconds=.15)
  self.assertLess(time.monotonic()-start,1)
if __name__=='__main__':unittest.main()
