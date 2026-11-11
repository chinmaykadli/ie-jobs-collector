"""Experimental streaming importer, isolated copy-only test. No production use."""
import json,sqlite3,pathlib,gzip
from sqlite_state import create_jobs,source_id,dump
class Stream:
 def __init__(self,f,max_value_chars=8*1024*1024): self.f=f;self.buf='';self.pos=0;self.end=False;self.decoder=json.JSONDecoder();self.max_value_chars=max_value_chars
 def more(self):
  chunk=self.f.read(65536);self.buf=self.buf[self.pos:]+chunk;self.pos=0
  if not chunk:self.end=True
  if len(self.buf)>self.max_value_chars:raise ValueError('Individual JSON value exceeds safe limit')
 def ws(self):
  while True:
   while self.pos<len(self.buf) and self.buf[self.pos].isspace():self.pos+=1
   if self.pos<len(self.buf) or self.end:return
   old=len(self.buf)-self.pos;self.more()
   if len(self.buf)==old:self.end=True
 def char(self,c):
  self.ws()
  if self.pos>=len(self.buf)or self.buf[self.pos]!=c:raise ValueError('Expected '+c)
  self.pos+=1
 def value(self):
  self.ws()
  while True:
   try:
    v,end=self.decoder.raw_decode(self.buf,self.pos)
    if (end==len(self.buf) or self.buf[end] not in ':,}] \t\r\n') and not self.end:self.more();continue
    if end<len(self.buf) and self.buf[end] not in ':,}] \t\r\n':raise ValueError('Invalid JSON token')
    self.pos=end;return v
   except json.JSONDecodeError:
    old=len(self.buf)-self.pos;self.more()
    if len(self.buf)==old:raise ValueError('Truncated JSON')
 def array(self):
  self.char('[');self.ws()
  if self.pos<len(self.buf)and self.buf[self.pos]==']':self.pos+=1;return
  while True:
   yield self.value();self.ws()
   if self.pos>=len(self.buf):raise ValueError('Truncated array')
   if self.buf[self.pos]==']':self.pos+=1;return
   self.char(',')
 def pairs(self):
  self.char('{');self.ws()
  if self.pos<len(self.buf)and self.buf[self.pos]=='}':self.pos+=1;return
  while True:
   k=self.value()
   if not isinstance(k,str):raise ValueError('Object key must be string')
   self.char(':');yield k
   self.ws()
   if self.buf[self.pos]=='}':self.pos+=1;return
   self.char(',')
def records(path,include_presence=False):
 op=gzip.open if str(path).endswith('.gz')else open
 with op(path,'rt',encoding='utf-8')as f:
  p=Stream(f)
  for section in p.pairs():
   if section in ['jobs','sources','desc_fetch']:
    if include_presence:yield 'section_presence',section,True
    for key in p.pairs():yield section,key,p.value()
   else:yield 'metadata',section,p.value()
  p.ws()
  if p.pos<len(p.buf):raise ValueError('Trailing data')
def import_state(source,destination):
 dest=pathlib.Path(destination);tmp=dest.with_suffix('.importing.sqlite')
 if dest.exists()or tmp.exists():raise FileExistsError('Refuse overwrite')
 db=sqlite3.connect(tmp)
 try:
  create_jobs(db)
  for t in ['sources','desc_fetch','metadata','section_presence']:db.execute('CREATE TABLE '+t+' (key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
  for table,key,value in records(source,include_presence=True):
   if table=='jobs':db.execute('INSERT INTO jobs(key,payload,source_id)VALUES(?,?,?)',(key,dump(value),source_id(key)))
   else:db.execute('INSERT INTO '+table+' VALUES(?,?)',(key,dump(value)))
  db.commit();db.close();tmp.replace(dest)
 except BaseException:
  db.close();tmp.unlink(missing_ok=True);raise
