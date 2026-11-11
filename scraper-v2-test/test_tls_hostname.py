import unittest,tempfile,pathlib,subprocess,ssl,threading,types
from unittest.mock import patch
from http.server import HTTPServer,BaseHTTPRequestHandler
from bounded_http import PublicHTTPSConnection
class TLS(unittest.TestCase):
 def test_trusted_certificate_wrong_hostname_is_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   d=pathlib.Path(d);cert=d/'cert.pem';key=d/'key.pem'
   subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=wrong.invalid','-addext','subjectAltName=DNS:wrong.invalid'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
   class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'fixture')
   server=HTTPServer(('127.0.0.1',0),H);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(str(cert),str(key));server.socket=ctx.wrap_socket(server.socket,server_side=True);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
   try:
    trusted=ssl.create_default_context(cafile=str(cert));connection=PublicHTTPSConnection('127.0.0.1',server.server_port,context=trusted,timeout=3)
    with patch('bounded_http.ipaddress.ip_address',return_value=types.SimpleNamespace(is_global=True)):
     with self.assertRaises(ssl.SSLCertVerificationError):connection.connect()
    connection.close()
   finally:server.shutdown();server.server_close();t.join()
if __name__=='__main__':unittest.main()
