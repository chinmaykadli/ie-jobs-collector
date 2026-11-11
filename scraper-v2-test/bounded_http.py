"""Copy-only bounded public HTTP reader. No cookies, authentication or retries."""
import urllib.request,urllib.error,io,time,zlib,socket,ipaddress,os,http.client,ssl
from urllib.parse import urlsplit

def check_public(url):
 u=urlsplit(url)
 if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in(None,443):raise ValueError('Only public HTTPS URLs are allowed')
 addresses=socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)
 if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Nonpublic address forbidden')
 return u
class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  old=check_public(req.full_url);new=check_public(newurl)
  if new.hostname.removeprefix('www.')!=old.hostname.removeprefix('www.'):raise ValueError('Cross-host redirect forbidden')
  # Different job paths must not be silently filed under the original URL.
  if (old.path.rstrip('/'),old.query)!=(new.path.rstrip('/'),new.query):raise ValueError('Redirect changed resource identity')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
class PublicHTTPSConnection(http.client.HTTPSConnection):
 def connect(self):
  # Pin the validated address on the actual socket, avoiding a second DNS lookup.
  addresses=socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)
  if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Nonpublic address forbidden')
  last=None
  for family,kind,proto,_,address in addresses:
   sock=socket.socket(family,kind,proto);sock.settimeout(self.timeout)
   try:sock.connect(address);self.sock=self._context.wrap_socket(sock,server_hostname=self.host);return
   except OSError as e:last=e;sock.close()
  raise last or OSError('No public address reachable')
class PublicHTTPSHandler(urllib.request.HTTPSHandler):
 def https_open(self,req):return self.do_open(PublicHTTPSConnection,req,context=self._context)
_OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),RestrictedRedirect(),PublicHTTPSHandler())
def public_open(request,timeout):
 check_public(request.full_url if isinstance(request,urllib.request.Request)else request)
 response=_OPENER.open(request,timeout=timeout)
 try:response.fp.raw._sock.settimeout(timeout)
 except AttributeError:
  response.close();raise RuntimeError('Unsupported HTTP socket layout; deadline cannot be enforced')
 return response
BASE_OPEN=public_open

def adjust_timeout(raw,start,total_seconds):
 remaining=total_seconds-(time.monotonic()-start)
 if remaining<=0:raise TimeoutError('Total request deadline')
 try:raw.fp.raw._sock.settimeout(remaining)
 except AttributeError:
  if BASE_OPEN is public_open:raise RuntimeError('Unsupported HTTP socket layout; deadline cannot be enforced')

def verify_end(raw,wire,decoder):
 length=raw.headers.get('Content-Length')
 if length is not None and int(length)!=wire:raise ValueError('Truncated Content-Length response')
 if decoder and decoder.unused_data:raise ValueError('Trailing gzip data forbidden')
class Response(io.BytesIO):
 def __init__(self,body,status,headers,url):super().__init__(body);self.status=status;self.headers=headers;self.url=url
 def getcode(self):return self.status
 def geturl(self):return self.url

def urlopen(request,timeout=20,max_bytes=50*1024*1024,total_seconds=40):
 start=time.monotonic();remaining=max(0.05,min(timeout or 20,total_seconds));raw=BASE_OPEN(request,timeout=remaining)
 try:
  status=raw.getcode();headers=raw.headers;url=raw.geturl();body=bytearray();wire=0
  if status!=200:raise ValueError('Unexpected HTTP status')
  encoding=(headers.get('Content-Encoding')or'').lower();decoder=zlib.decompressobj(16+zlib.MAX_WBITS)if encoding=='gzip'else None
  if encoding not in ('','identity','gzip'):raise ValueError('Unsupported content encoding')
  while True:
   if time.monotonic()-start>total_seconds:raise TimeoutError('Total request deadline')
   adjust_timeout(raw,start,total_seconds)
   chunk=raw.read1(65536) if hasattr(raw,'read1') else raw.read(65536)
   if not chunk:break
   wire+=len(chunk)
   if wire>max_bytes:raise ValueError('Wire response exceeds safe byte limit')
   part=decoder.decompress(chunk,max_bytes-len(body)+1)if decoder else chunk
   body.extend(part)
   if len(body)>max_bytes:raise ValueError('Decoded response exceeds safe byte limit')
  verify_end(raw,wire,decoder)
  if decoder:
   body.extend(decoder.flush(max_bytes-len(body)+1))
   if len(body)>max_bytes or not decoder.eof:raise ValueError('Oversized or truncated gzip response')
  if time.monotonic()-start>total_seconds:raise TimeoutError('Total request deadline')
  return Response(body,status,headers,url)
 finally:raw.close()

# Disk spool for adapters whose top-level array is large (notably Lever).
# The same wire/expanded limits apply, but the body is never accumulated in RAM.
def download(request,destination,timeout=20,max_bytes=50*1024*1024,total_seconds=40):
 import pathlib
 destination=pathlib.Path(destination);temporary=destination.with_name(destination.name+'.tmp');start=time.monotonic();raw=BASE_OPEN(request,timeout=min(timeout,total_seconds));wire=expanded=0
 try:
  status=raw.getcode()
  if status!=200:raise ValueError('Unexpected HTTP status')
  encoding=(raw.headers.get('Content-Encoding')or'').lower()
  if encoding not in ('','identity','gzip'):raise ValueError('Unsupported content encoding')
  decoder=zlib.decompressobj(16+zlib.MAX_WBITS)if encoding=='gzip'else None
  with temporary.open('wb')as f:
   while True:
    if time.monotonic()-start>total_seconds:raise TimeoutError('Total request deadline')
    adjust_timeout(raw,start,total_seconds)
    chunk=raw.read1(65536)if hasattr(raw,'read1')else raw.read(65536)
    if not chunk:break
    wire+=len(chunk)
    if wire>max_bytes:raise ValueError('Wire response exceeds safe byte limit')
    part=decoder.decompress(chunk,max_bytes-expanded+1)if decoder else chunk;expanded+=len(part)
    if expanded>max_bytes:raise ValueError('Decoded response exceeds safe byte limit')
    f.write(part)
   verify_end(raw,wire,decoder)
   if decoder:
    tail=decoder.flush(max_bytes-expanded+1);expanded+=len(tail)
    if expanded>max_bytes or not decoder.eof:raise ValueError('Oversized or truncated gzip response')
    f.write(tail)
  if time.monotonic()-start>total_seconds:raise TimeoutError('Total request deadline')
  os.replace(temporary,destination)
  return status,expanded
 except BaseException:
  temporary.unlink(missing_ok=True);raise
 finally:raw.close()
