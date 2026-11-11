"""File-backed top-level array. List-compatible only at the adapter read boundary.
No indexing or mutating: normalize one record at a time. Does not silently clip.
"""
import pathlib
from import_state import Stream
class DiskArray(list):
 def __init__(self,path,capture_envelope=False):self.path=pathlib.Path(path);self.envelope=capture_envelope;self.count=None
 def __iter__(self):
  with self.path.open('r',encoding='utf-8')as f:
   p=Stream(f)
   if not self.envelope:yield from p.array()
   else:
    found=False
    for key in p.pairs():
     if key=='payload':
      if found:raise ValueError('Duplicate payload key')
      found=True;yield from p.array()
     else:p.value()
    if not found:raise ValueError('Missing captured payload')
   p.ws()
   if p.pos<len(p.buf):raise ValueError('Trailing JSON data')
 def __len__(self):
  if self.count is None:self.count=sum(1 for _ in self)
  return self.count
 def __getitem__(self,index):raise TypeError('Streaming payload cannot be indexed')
 def append(self,*a):raise TypeError('Read-only streaming payload')
 def extend(self,*a):raise TypeError('Read-only streaming payload')
