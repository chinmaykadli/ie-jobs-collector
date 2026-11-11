"""Copy-only legacy Intel identity quarantine. Never edits an input or live store.
The Spotlight Job label merged distinct postings. Archive it exactly and omit it
from the new import state, without asserting a vacancy closure or inventing IDs.
"""
import argparse,hashlib,json,os,pathlib,shutil,tempfile
from import_state import records
from generation_runner import syncdir,syncfile
from sqlite_state import dump
TARGET='workday:intel:Spotlight Job'

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()

def plan(source):
 source=pathlib.Path(source).resolve(strict=True);found=[];count=0
 for table,key,value in records(source):
  if table=='jobs':
   count+=1
   if key==TARGET:
    if value.get('ats')!='workday' or value.get('id')!='Spotlight Job':raise ValueError('Unexpected collision record shape')
    found.append({'key':key,'record':value,'reason':'LEGACY_NONUNIQUE_PROVIDER_LABEL_IDENTITY_UNVERIFIED'})
 return {'schema':1,'input_sha256':digest(source),'input_jobs':count,'quarantine':found,'output_jobs':count-len(found),'semantics':'IDENTITY_QUARANTINE_NOT_JOB_CLOSURE','source_unchanged':'NOT_CHECKED'}

def record_digest(source,skip_target=False):
 h=hashlib.sha256();count=0
 for t,k,v in records(source,include_presence=True):
  if skip_target and t=='jobs' and k==TARGET:continue
  encoded=dump([t,k,v]).encode();h.update(str(len(encoded)).encode()+b':'+encoded);count+=1
 return h.hexdigest(),count

class MigrationDurabilityError(OSError):
 committed=True

def rename_noreplace(source,destination):
 # The candidate targets Linux. Never silently downgrade to racy os.rename.
 import ctypes
 libc=ctypes.CDLL(None,use_errno=True)
 if not hasattr(libc,'renameat2'):raise RuntimeError('Atomic no-replace rename unavailable')
 fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
 if fn(-100,os.fsencode(source),-100,os.fsencode(destination),1)!=0:
  err=ctypes.get_errno()
  if err==17:raise FileExistsError(err,'Destination exists',str(destination))
  raise OSError(err,os.strerror(err),str(destination))

def write_output(source,target):
 with target.open('w',encoding='utf-8') as out:
  current=None;first_section=True;first_value=True;out.write('{')
  for table,key,value in records(source,include_presence=True):
   if table=='section_presence':
    if current is not None:out.write('}');current=None
    if not first_section:out.write(',')
    out.write(dump(key)+':{');current=key;first_section=False;first_value=True
   elif table=='metadata':
    if current is not None:out.write('}');current=None
    if not first_section:out.write(',')
    out.write(dump(key)+':'+dump(value));first_section=False
   else:
    if table!=current:raise ValueError('Unexpected stream section')
    if table=='jobs' and key==TARGET:continue
    if not first_value:out.write(',')
    out.write(dump(key)+':'+dump(value));first_value=False
  if current is not None:out.write('}')
  out.write('}')

def migrate(source,destination,expected_sha256):
 source=pathlib.Path(source).resolve(strict=True);dest=pathlib.Path(destination)
 if dest.exists() or dest.is_symlink():raise FileExistsError('Never overwrite destination')
 dest.parent.mkdir(parents=True,exist_ok=True)
 stage=pathlib.Path(tempfile.mkdtemp(prefix='.intel-migration-',dir=dest.parent));stage.chmod(0o700)
 try:
  snapshot=stage/('input-state.json.gz' if str(source).endswith('.gz') else 'input-state.json')
  shutil.copyfile(source,snapshot);snapshot.chmod(0o600)
  if digest(snapshot)!=expected_sha256:raise ValueError('Input snapshot hash mismatch')
  report=plan(snapshot)
  write_output(snapshot,stage/'state.json')
  checked=plan(stage/'state.json')
  if checked['input_jobs']!=report['output_jobs'] or checked['quarantine']:raise ValueError('Output verification failed')
  if record_digest(snapshot,skip_target=True)!=record_digest(stage/'state.json'):raise ValueError('Output record equality failed')
  report['all_unaffected_records_equal']=True
  report['output_sha256']=digest(stage/'state.json')
  if digest(source)!=expected_sha256:raise ValueError('Input changed during migration')
  report['source_unchanged']=True
  (stage/'quarantine.json').write_text(json.dumps(report['quarantine'],ensure_ascii=True,indent=2))
  (stage/'migration-report.json').write_text(json.dumps(report,ensure_ascii=True,indent=2))
  for p in stage.iterdir():p.chmod(0o600);syncfile(p)
  syncdir(stage);rename_noreplace(stage,dest)
  try:syncdir(dest.parent)
  except OSError as e:
   err=MigrationDurabilityError('Output committed, parent directory durability unconfirmed');err.destination=str(dest);raise err from e
  return report
 except BaseException:
  if stage.exists():shutil.rmtree(stage)
  raise

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--destination');p.add_argument('--input-sha256');a=p.parse_args()
 if a.destination:
  if not a.input_sha256:p.error('--input-sha256 is required for copy migration')
  result=migrate(a.source,a.destination,a.input_sha256)
 else:result=plan(a.source)
 print(json.dumps({k:v for k,v in result.items() if k!='quarantine'},indent=2));print('quarantined_keys:',[r['key'] for r in result['quarantine']])
