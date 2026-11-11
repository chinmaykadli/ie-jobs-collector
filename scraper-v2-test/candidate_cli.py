"""Copy-only candidate entrypoint. Does not schedule, deploy or deliver messages.
Published generation identity, never a return body, is the source of truth.
"""
import pathlib,json,os,sys,argparse,time,hashlib,uuid
import ingest,ats_extra
from sqlite_bridge import install
from generation_runner import run,current,verify_generation,CommitDurabilityError
from screen_policy import pinned,load_policy

def identity(root):
 try:
  p=current(root);return p.name if p else None
 except FileNotFoundError:return None

def storage_stats(root):
 try:
  import stat
  out={}
  for name in ['superseded','abandoned','quarantine']:
   folder=pathlib.Path(root)/name
   if folder.is_symlink():continue
   entries=list(folder.iterdir())if folder.exists()else[];total=0;count=0
   for entry in entries:
    if entry.is_symlink():continue
    count+=1
    if entry.is_file():total+=entry.lstat().st_size;continue
    for parent,dirs,files in os.walk(entry,followlinks=False,onerror=lambda e:(_ for _ in()).throw(e)):
     dirs[:]=[n for n in dirs if not(pathlib.Path(parent)/n).is_symlink()]
     for n in files:
      p=pathlib.Path(parent)/n;info=p.lstat()
      if stat.S_ISREG(info.st_mode):total+=info.st_size
   out[name]={'count':count,'bytes':total}
  return out
 except Exception as e:return {'error':type(e).__name__}

def ops(root,record):
 p=pathlib.Path(root)/'ops.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists()and p.stat().st_size>1024*1024:
  p.replace(p.with_name('ops.previous.jsonl'))
 with p.open('a',encoding='utf-8')as f:f.write(json.dumps(record,ensure_ascii=True,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())

def collect(root,sources,policy=None,fetcher=None,expected_policy_sha256=None):
 install(ingest)  # Programmatic collect uses the same explicit SQLite path as the CLI.
 ingest.desc_enricher=None  # No implicit live detail path in this list-only candidate.
 started=time.time();run_id=uuid.uuid4().hex;before=None
 try:
  before=identity(root)
  ingest.validate_sources(sources)
  if policy is not None:pinned(policy,expected_policy_sha256)
  report=run(root,sources,ingest.ingest,fetcher=fetcher,policy=policy,run_id=run_id);visible=current(root);published=pathlib.Path(root)/'generations'/report['published_generation'];verify_generation(published)
  meta=json.loads((published/'manifest.json').read_text())
  if meta.get('run_id')!=run_id:raise ValueError('Visible generation belongs to another run')
  record={'completed':True,'run_id':run_id,'visible_generation':visible.name,'own_published_generation':published.name,'pointer_changed':visible.name!=before,'durability':'DIRECTORY_FSYNC_CONFIRMED','post_commit_warnings':report.get('post_commit_warnings',[]),'seconds':round(time.time()-started,3),'storage':storage_stats(root)}
 except BaseException as e:
  after='UNVERIFIABLE';own=None
  try:
   visible=current(root);after=visible.name if visible else None
   if visible:own=json.loads((visible/'manifest.json').read_text()).get('run_id')==run_id
  except Exception:pass
  record={'completed':False,'run_id':run_id,'visible_generation':after,'pointer_changed':after!=before,'error':type(e).__name__,'own_generation_visible':own,'publication_may_have_committed':own if own is not None else 'UNKNOWN','durability':'UNCONFIRMED'if isinstance(e,CommitDurabilityError)else'DIRECTORY_FSYNC_CONFIRMED'if own and getattr(e,'committed',False)else'CHECK_CURRENT','seconds':round(time.time()-started,3),'storage':storage_stats(root)}
  try:ops(root,record)
  except OSError:record['ops_log_failed']=True
  if isinstance(e,(KeyboardInterrupt,SystemExit)):raise
  return record
 try:ops(root,record)
 except OSError:record['ops_log_failed']=True
 return record
def check_runtime():
 if sys.version_info[:3]!=(3,10,12):raise RuntimeError('Pinned runtime Python 3.10.12 required')

if __name__=='__main__':
 check_runtime()
 p=argparse.ArgumentParser();p.add_argument('--store',required=True);p.add_argument('--sources',default='sources.json');p.add_argument('--policy');p.add_argument('--policy-sha256');a=p.parse_args();install(ingest)
 result=collect(a.store,json.loads(pathlib.Path(a.sources).read_text()),load_policy(pathlib.Path(a.policy).read_text())if a.policy else None,expected_policy_sha256=a.policy_sha256);print(json.dumps(result,indent=2));raise SystemExit(0 if result['completed']else 1)
