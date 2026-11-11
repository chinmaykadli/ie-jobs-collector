"""Hourly list-only soak. No deploy, data publication, email or applications."""
import argparse,pathlib,json,time,os,sys,subprocess,resource,hashlib,collections,sqlite3
ROOT=pathlib.Path(__file__).resolve().parent
STATE=ROOT/'soak-state'
def emit(record):
 print(json.dumps(record,sort_keys=True),flush=True)
 with (STATE/'evidence.jsonl').open('a')as f:f.write(json.dumps(record,sort_keys=True)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--segment',type=int,required=True);a=p.parse_args()
 if not 0<=a.segment<=4:raise ValueError('Invalid segment')
 STATE.mkdir(exist_ok=True)
 control=STATE/'control.json'
 if a.segment==0:
  if control.exists():raise ValueError('Unexpected existing state')
  control.write_text(json.dumps({'started_at':time.time(),'next_cycle':0}))
 if not control.exists():raise ValueError('Missing required continuation state')
 meta=json.loads(control.read_text())
 if meta['next_cycle']!=a.segment*5:raise ValueError('Continuation cycle mismatch')
 from generation_runner import current,verify_generation,code_digest
 digest=code_digest()
 if meta.get('code_digest',digest)!=digest:raise ValueError('Code changed during soak')
 meta['code_digest']=digest
 for cycle in range(a.segment*5,a.segment*5+5):
  due=meta['started_at']+cycle*3600
  time.sleep(max(0,due-time.time()))
  for count,filename in [(135,'sources.json'),(149,'sources-149.json')]:
   sources=json.loads((ROOT/filename).read_text());assert len(sources)==count
   store=STATE/str(count);before=current(store)
   oldseq=json.loads((before/'manifest.json').read_text())['seq']if before else 0
   if oldseq!=cycle:raise ValueError('Generation continuity mismatch')
   start=time.time()
   def cap():resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
   child=subprocess.Popen([sys.executable,'candidate_cli.py','--store',str(store),'--sources',filename],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,preexec_fn=cap)
   # wait4 gives this child's measured RSS, rather than a prior child's peak.
   try:
    out,err=child.communicate(timeout=1500)
   except subprocess.TimeoutExpired:
    child.kill();out,err=child.communicate();raise RuntimeError('Full live cycle exceeded 25 minute bound')
   rss=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
   if child.returncode:
    emit({'cycle':cycle,'sources':count,'completed':False,'exit':child.returncode,'seconds':time.time()-start,'stderr_tail':err[-1500:],'stdout_tail':out[-1500:]});raise RuntimeError('Candidate failed; soak stopped')
   result=json.loads(out);assert result['completed']
   latest=current(store);verify_generation(latest)
   manifest=json.loads((latest/'manifest.json').read_text());assert manifest['seq']==cycle+1
   assert manifest['code_version']==digest
   health=json.loads((latest/'health.json').read_text());queue=json.loads((latest/'raw-irish-queue.json').read_text());display=json.loads((latest/'display.json').read_text());assert display['jobs']==[] and display['policy_available']is False
   with sqlite3.connect('file:'+str(latest/'state.sqlite')+'?mode=ro',uri=True)as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
   emit({'cycle':cycle,'source_count':count,'completed':True,'seq':manifest['seq'],'generation':latest.name,'seconds':round(time.time()-start,3),'peak_children_rss_kib_cumulative':rss,'address_space_cap_mib':256,'irish_raw':len(queue),'source_health':dict(collections.Counter(r['status']for r in health['source_health'])),'description_states':dict(collections.Counter(r.get('description_state')for r in queue)),'code_digest':digest,'checked_at':health.get('checked_at'),'policy':'NONE_FAIL_CLOSED','detail_enrichment':False})
  meta['next_cycle']=cycle+1;control.write_text(json.dumps(meta))
 elapsed=time.time()-meta['started_at']
 if a.segment==4:
  if elapsed<86400:raise ValueError('Not yet a genuine 24 hours')
  emit({'soak_completed':True,'cycles_per_source_set':25,'elapsed_seconds':elapsed,'started_at':meta['started_at'],'completed_at':time.time(),'note':'State carried between five standard-runner jobs; no continuous-process claim'})
 if sum(p.stat().st_size for p in STATE.rglob('*')if p.is_file()and not p.is_symlink())>6*1024**3:raise RuntimeError('Raw state exceeds disk safety cap')
if __name__=='__main__':main()
