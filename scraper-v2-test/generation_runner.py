"""Copy-only immutable generations. Pointer swap is the logical commit point.
No live workflow uses this code. Power-loss durability remains untested.
"""
import os,json,pathlib,shutil,fcntl,uuid,sqlite3,hashlib,warnings,time
from urllib.parse import urlsplit
from datetime import datetime,timezone
from contextlib import contextmanager
from screen_policy import validate,company,clean
REQUIRED={'state.sqlite','state.json','health.json','last-changes.json','raw-irish-queue.json','changes.jsonl','display.json'}
class CommitDurabilityError(OSError):committed=True
class PostCommitError(RuntimeError):committed=True

def syncdir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def syncfile(p):
 with open(p,'rb')as f:os.fsync(f.fileno())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb')as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def code_digest():
 root=pathlib.Path(__file__).parent;h=hashlib.sha256()
 files=sorted(root.glob('*.py'))+sorted((root/'private-ui').glob('*'))
 for p in files:
  if p.is_file():h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
 return h.hexdigest()
def current(root):
 root=pathlib.Path(root);p=root/'current'
 if not os.path.lexists(p):
  if (root/'generations').exists()and any((root/'generations').iterdir()):raise ValueError('Missing current pointer in nonempty store')
  return None
 if not p.is_symlink():raise ValueError('Current must be a symlink')
 resolved=p.resolve(strict=True);base=(root/'generations').resolve()
 if resolved.parent!=base or not resolved.is_dir():raise ValueError('Current outside generation store')
 m=json.loads((resolved/'manifest.json').read_text(encoding='utf-8'))
 if m.get('generation')!=resolved.name or type(m.get('seq'))is not int:raise ValueError('Generation identity mismatch')
 return resolved
@contextmanager
def writer(root):
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
 with open(root/'writer.lock','a+b')as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('Collector already running')
  try:yield
  finally:fcntl.flock(f,fcntl.LOCK_UN)
def remove_tree(p):
 p=pathlib.Path(p)
 for x in p.rglob('*'):
  if not x.is_symlink()and x.is_dir():x.chmod(0o700)
 p.chmod(0o700);shutil.rmtree(p)
def trim_abandoned(root):
 for p in sorted(root.iterdir(),key=lambda p:p.lstat().st_mtime,reverse=True)[2:]:
  if p.is_symlink()or not p.is_dir():p.unlink()
  else:remove_tree(p)
def aware_timestamp(stamp):
 try:
  dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
  if dt.tzinfo is None or dt.utcoffset()is None:raise ValueError('Timezone required')
  return dt.timestamp()
 except (TypeError,ValueError,AttributeError):return None

def project(stage,policy=None,seq=None):
 checked=validate(policy)
 health=json.loads((stage/'health.json').read_text(encoding='utf-8'))
 stamp=health.get('checked_at')
 feed_as_of=aware_timestamp(stamp)
 sources={h['source']:{'status':'ZERO_OR_DROP_SUSPECT'if 'SUSPECT_ZERO_OR_DROP'in h.get('failure_reason','')else h.get('status','UNVERIFIED'),'last_success_at':h.get('last_success_at'),'checked_at':h.get('checked_at')}for h in health.get('source_health',[])}
 out={'schema_version':1,'qualification_state':'NOT_ASSESSED','policy_available':checked is not None,'policy_sha256':checked['sha256']if checked else None,'generated_at':time.time(),'feed_as_of':feed_as_of,'seq':seq,'sources':{},'jobs':[]}
 if checked:
  for j in json.loads((stage/'raw-irish-queue.json').read_text(encoding='utf-8')):
   # Agencies do not establish the hiring employer's identity.
   if j.get('ats')=='agency' or '(agency)'in str(j.get('company','')).casefold():continue
   if not company(j.get('company',''))or company(j.get('company',''))in checked['blocked']:continue
   row={k:j.get(k)for k in ['key','company','title','location','job_url','description_state','description_freshness','location_state','active_state','availability','last_success_at']}
   for key,limit in [('company',200),('title',300),('location',500)]:row[key]=clean(row.get(key),limit)
   sid=':'.join(str(j.get('key','')).split(':')[:2]);source=sources.get(sid,{'status':'NOT_CHECKED','last_success_at':None})
   out['sources'][sid]=source
   row.update(source_id=sid,source_status=source['status'],source_last_success_at=source.get('last_success_at'),source_checked_at=source.get('checked_at'))
   row['listing_stale']=bool(j.get('stale',False))or source['status']not in('OK_NONEMPTY','OK_ZERO')
   row['key']=clean(row.get('key'),512)
   url=row.get('job_url')
   try:
    u=urlsplit(url)if isinstance(url,str)and len(url)<=2048 else None
    row['job_url']=url if u and u.scheme=='https'and u.hostname and not u.username and not u.password else None
   except ValueError:row['job_url']=None
   out['jobs'].append(row)
 (stage/'display.json').write_text(json.dumps(out,ensure_ascii=True,allow_nan=False),encoding='utf-8')
 return out['policy_sha256']
def verify_generation(path):
 path=pathlib.Path(path);m=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
 if m.get('generation')!=path.name or m.get('schema')!=1 or type(m.get('seq'))is not int:raise ValueError('Generation identity/schema mismatch')
 if set(m.get('files',{}))!=REQUIRED or {p.name for p in path.iterdir()}!=REQUIRED|{'manifest.json'}:raise ValueError('Unexpected or missing generation files')
 for name,info in m['files'].items():
  if pathlib.Path(name).name!=name or(path/name).is_symlink():raise ValueError('Unsafe generation path')
  if sha(path/name)!=info['sha256']or(path/name).stat().st_size!=info['bytes']:raise ValueError('Generation file integrity mismatch: '+name)
 return True

def run(root,sources,ingest_fn,fetcher=None,fault=None,policy=None,run_id=None):
 root=pathlib.Path(root)
 def checkpoint(name):
  if fault:fault(name)
 with writer(root):
  gens=root/'generations';gens.mkdir(exist_ok=True);abandoned=root/'abandoned';abandoned.mkdir(exist_ok=True)
  # Recover only a fully validated sole first generation. No history is reset.
  if not os.path.lexists(root/'current')and any(gens.iterdir()):
   candidates=list(gens.iterdir())
   if len(candidates)!=1:raise ValueError('Missing current pointer requires restore review')
   candidate=candidates[0];verify_generation(candidate)
   initial=json.loads((candidate/'manifest.json').read_text())
   if initial['seq']!=1 or initial.get('parent')is not None:raise ValueError('Missing current pointer after history exists')
   link=root/'.next-bootstrap';link.unlink(missing_ok=True);link.symlink_to(pathlib.Path('generations')/candidate.name);os.replace(link,root/'current');syncdir(root)
  old=current(root)
  if old:verify_generation(old)
  oldmeta=json.loads((old/'manifest.json').read_text())if old else {'seq':0}
  superseded=root/'superseded';superseded.mkdir(exist_ok=True)
  high_path=root/'seq_high_water'
  high=int(high_path.read_text())if high_path.exists()else 0
  for folder in [gens,superseded,abandoned]:
   for candidate in folder.iterdir():
    try:high=max(high,int(json.loads((candidate/'manifest.json').read_text())['seq']))
    except (OSError,ValueError,KeyError,TypeError):pass
  # Higher generations may have been visible before rollback/power loss: preserve them.
  quarantine=root/'quarantine';quarantine.mkdir(exist_ok=True)
  for p in list(gens.iterdir()):
   if p!=old:
    try:
     if not p.is_dir()or p.is_symlink():raise ValueError('Unexpected generation entry')
     m=json.loads((p/'manifest.json').read_text())
     if not isinstance(m,dict)or type(m.get('seq'))is not int:raise ValueError('Invalid manifest sequence')
     verify_generation(p)
    except (OSError,ValueError,TypeError,KeyError):
     if p.is_dir()and not p.is_symlink():p.chmod(0o700)
     p.rename(quarantine/(p.name+'-'+uuid.uuid4().hex));syncdir(gens);syncdir(quarantine);continue
    if m['seq']>oldmeta['seq']:p.chmod(0o700);p.rename(superseded/p.name);syncdir(gens);syncdir(superseded)
  for p in root.glob('.stage-*'):p.rename(abandoned/p.name)
  for p in root.glob('.next-*'):p.unlink()
  trim_abandoned(abandoned)
  previous_bytes=sum(p.stat().st_size for p in old.iterdir())if old else 0
  needed=max(1024**3,previous_bytes*3)
  if shutil.disk_usage(root).free<needed:raise OSError('Insufficient free disk for safe generation')
  seq=max(high,oldmeta['seq'])+1;ident=str(seq).zfill(8)+'-'+uuid.uuid4().hex;stage=root/('.stage-'+ident);stage.mkdir();committed=False;post_commit_warnings=[]
  reservation=root/'.high-water-next';reservation.write_text(str(seq));syncfile(reservation);os.replace(reservation,high_path);syncdir(root)
  try:
   if old:
    source=sqlite3.connect('file:'+str(old/'state.sqlite')+'?mode=ro&immutable=1',uri=True);dest=sqlite3.connect(stage/'state.sqlite')
    try:source.backup(dest)
    finally:dest.close();source.close()
   checkpoint('before_collect');result=ingest_fn(sources,stage,fetcher=fetcher);checkpoint('after_collect');policy_hash=project(stage,policy,seq)
   db=sqlite3.connect('file:'+str(stage/'state.sqlite')+'?mode=ro',uri=True)
   try:
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':raise ValueError('Database integrity/journal mode failure')
   finally:db.close()
   if {p.name for p in stage.iterdir()}!=REQUIRED:raise ValueError('Unexpected or missing stage files')
   files={p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in stage.iterdir()}
   manifest={'generation':ident,'seq':seq,'parent':old.name if old else None,'files':files,'schema':1,'code_version':code_digest(),'policy_sha256':policy_hash,'run_id':run_id}
   (stage/'manifest.json').write_text(json.dumps(manifest,allow_nan=False),encoding='utf-8')
   for p in stage.iterdir():syncfile(p);p.chmod(0o444)
   syncdir(stage);checkpoint('before_generation_rename')
   final=gens/ident;stage.rename(final);final.chmod(0o555);syncdir(gens);checkpoint('before_pointer_swap');link=root/('.next-'+ident);link.symlink_to(pathlib.Path('generations')/ident)
   os.replace(link,root/'current');committed=True
   try:syncdir(root)
   except OSError as e:
    err=CommitDurabilityError('Pointer swapped but directory durability unconfirmed');err.generation=ident;raise err from e
   result=dict(result)if isinstance(result,dict)else {'ingest_result_type':type(result).__name__}
   result.update(published_generation=ident,publication_state='COMMITTED',seq=seq,run_id=run_id)
   checkpoint('after_pointer_swap')
   # Pruning has its own short lock, never the long collection lock.
   try:
    with open(root/'prune.lock','a+b')as f:
     try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:pass
     else:
      prior=sorted((p for p in gens.iterdir()if p!=final),key=lambda p:json.loads((p/'manifest.json').read_text())['seq'],reverse=True)
      for p in prior[2:]:
       checkpoint('before_prune_rename');trash=abandoned/('pruned-'+p.name);p.chmod(0o700);p.rename(trash);syncdir(gens);checkpoint('after_prune_rename');remove_tree(trash);checkpoint('after_prune_delete')
      fcntl.flock(f,fcntl.LOCK_UN)
    trim_abandoned(abandoned)
   except OSError as e:post_commit_warnings.append(type(e).__name__);warnings.warn('Committed generation; post-commit pruning failed: '+str(e))
   if isinstance(result,dict):result['post_commit_warnings']=post_commit_warnings
   return result
  except BaseException as e:
   e.generation=ident;e.run_id=run_id
   if stage.exists():
    try:remove_tree(stage)
    except OSError as cleanup:warnings.warn('Stage cleanup failed: '+type(cleanup).__name__)
   if committed and not getattr(e,'committed',False) and isinstance(e,Exception):
    err=PostCommitError('Generation committed; post-commit step failed');err.generation=ident;raise err from e
   raise
@contextmanager
def reader(root):
 # Hold only the prune lock. Collection proceeds while old immutable files are read.
 root=pathlib.Path(root)
 with open(root/'prune.lock','a+b')as f:
  fcntl.flock(f,fcntl.LOCK_SH)
  try:yield current(root)
  finally:fcntl.flock(f,fcntl.LOCK_UN)
