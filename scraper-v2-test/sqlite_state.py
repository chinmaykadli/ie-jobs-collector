"""Detached-record SQLite store. Call jobs[key] = changed_record explicitly.
Not a transparent identity-preserving Python dictionary. Copy-only prototype.
"""
import json,sqlite3,pathlib
from collections.abc import MutableMapping

def dump(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,separators=(',',':'))
def create_jobs(db):
 db.execute('CREATE TABLE jobs (seq INTEGER PRIMARY KEY,key TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,source_id TEXT NOT NULL)')
 db.execute('CREATE INDEX jobs_source_seq ON jobs(source_id,seq)')
def source_id(key):
 parts=key.split(':',2)
 if len(parts)!=3 or not all(parts):raise ValueError('Invalid job key')
 return ':'.join(parts[:2])
def upgrade_jobs(db):
 if 'seq' in {r[1]for r in db.execute('pragma table_info(jobs)')}:return
 db.execute('ALTER TABLE jobs RENAME TO legacy_jobs');create_jobs(db)
 for key,payload in db.execute('SELECT key,payload FROM legacy_jobs ORDER BY rowid'):
  db.execute('INSERT INTO jobs(key,payload,source_id)VALUES(?,?,?)',(key,payload,source_id(key)))
 db.execute('DROP TABLE legacy_jobs')
class Jobs(MutableMapping):
 def __init__(self,db,writable=False):
  self.db,self.writable=db,writable;self.modern='seq'in {r[1]for r in db.execute('pragma table_info(jobs)')}
 def __len__(self):return self.db.execute('SELECT count(*)FROM jobs').fetchone()[0]
 def __contains__(self,key):return self.db.execute('SELECT 1 FROM jobs WHERE key=?',(key,)).fetchone()is not None
 def __iter__(self):return iter([r[0]for r in self.db.execute('SELECT key FROM jobs ORDER BY '+('seq'if self.modern else'rowid'))])
 def __getitem__(self,key):
  row=self.db.execute('SELECT payload FROM jobs WHERE key=?',(key,)).fetchone()
  if row is None:raise KeyError(key)
  return json.loads(row[0])
 def __setitem__(self,key,value):
  if not self.writable:raise TypeError('Read-only original state')
  self.db.execute('INSERT INTO jobs(key,payload,source_id)VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',(key,dump(value),source_id(key)))
 def __delitem__(self,key):
  if not self.writable:raise TypeError('Read-only original state')
  c=self.db.execute('DELETE FROM jobs WHERE key=?',(key,))
  if not c.rowcount:raise KeyError(key)
 def setdefault(self,*args):raise TypeError('Detached store: read, edit, then explicitly assign the record')
 def items(self):
  for key in self:yield key,self[key]
 def source_items(self,sid):
  if self.modern:keys=[r[0]for r in self.db.execute('SELECT key FROM jobs WHERE source_id=? ORDER BY seq',(sid,))]
  else:
   prefix=sid+':';keys=[r[0]for r in self.db.execute('SELECT key FROM jobs WHERE substr(key,1,?)=? ORDER BY rowid',(len(prefix),prefix))]
  for key in keys:yield key,self[key]
 def values(self):
  for _,v in self.items():yield v

def metadata(db):
 result={k:json.loads(v)for k,v in db.execute('SELECT * FROM metadata')}
 present={r[0]for r in db.execute('SELECT key FROM section_presence')}if db.execute("SELECT count(*)FROM sqlite_master WHERE name='section_presence'").fetchone()[0]else {'sources','desc_fetch'}
 for section in ['sources','desc_fetch']:
  if section in present:result[section]={k:json.loads(v)for k,v in db.execute('SELECT * FROM '+section)}
 return result
class StateTrial:
 def __init__(self,path):
  self.finished=False;self.path=pathlib.Path(path);self.work=self.path.with_suffix('.working.sqlite')
  if self.work.exists():raise FileExistsError('Unfinished isolated trial exists')
  self.original=sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)
  try:
   self.db=sqlite3.connect(self.work,isolation_level=None);self.original.backup(self.db)
   self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA synchronous=FULL');self.db.execute('BEGIN IMMEDIATE');upgrade_jobs(self.db)
   self.old=metadata(self.original);self.old['jobs']=Jobs(self.original)
   self.state=metadata(self.db);self.state['jobs']=Jobs(self.db,True)
  except BaseException:
   if hasattr(self,'db'):self.db.close()
   self.original.close();self.work.unlink(missing_ok=True);raise
 def __enter__(self):return self
 def __exit__(self,typ,value,traceback):
  if not self.finished:self.abort()
  return False
 def export_json(self,path):
  with open(path,'w',encoding='utf-8')as f:
   f.write('{"jobs":{');first=True
   for key,value in self.state['jobs'].items():
    if not first:f.write(',')
    first=False;f.write(dump(key)+':'+dump(value))
   f.write('}')
   for key,value in self.state.items():
    if key!='jobs':f.write(','+dump(key)+':'+dump(value))
   f.write('}')
 def commit(self):
  self.db.execute('CREATE TABLE IF NOT EXISTS section_presence(key TEXT PRIMARY KEY,payload TEXT NOT NULL)');self.db.execute('DELETE FROM section_presence')
  self.db.executemany('INSERT INTO section_presence VALUES(?,?)',[(k,'true')for k in ['jobs','sources','desc_fetch']if k in self.state])
  for section in ['sources','desc_fetch']:
   self.db.execute('DELETE FROM '+section);self.db.executemany('INSERT INTO '+section+' VALUES(?,?)',[(k,dump(v))for k,v in self.state.get(section,{}).items()])
  self.db.execute('DELETE FROM metadata');self.db.executemany('INSERT INTO metadata VALUES(?,?)',[(k,dump(v))for k,v in self.state.items()if k not in ['jobs','sources','desc_fetch']])
  self.db.execute('PRAGMA user_version=1');self.db.execute('COMMIT');self.db.close();self.original.close();self.work.replace(self.path);self.finished=True
 def abort(self):
  self.db.close();self.original.close();self.work.unlink(missing_ok=True);self.finished=True
