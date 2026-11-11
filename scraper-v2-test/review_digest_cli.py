"""Copy-only source-state review ledger. Does not write a generation or send mail."""
import argparse,json,pathlib,os,tempfile
from generation_runner import syncfile,syncdir
from intel_legacy_migration import rename_noreplace
from import_state import records
from screen_policy import load_policy
from review_policy import build_digest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--policy',required=True);p.add_argument('--policy-sha256',required=True);p.add_argument('--output',required=True);p.add_argument('--screen-policy',required=True);p.add_argument('--screen-policy-sha256',required=True);a=p.parse_args();dest=pathlib.Path(a.output)
 policy=load_policy(pathlib.Path(a.policy).read_text(encoding='utf-8'))
 jobs=[v for t,k,v in records(a.state) if t=='jobs' and v.get('irish_location_match') is True]
 screen=load_policy(pathlib.Path(a.screen_policy).read_text(encoding='utf-8'))
 result=build_digest(jobs,policy,a.policy_sha256,screen,a.screen_policy_sha256)
 # No overwrite, no inferred publication. This is a local review file only.
 dest.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.review-digest-',dir=dest.parent);tmp=pathlib.Path(tmp)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=True,allow_nan=False,indent=2)
  syncfile(tmp);rename_noreplace(tmp,dest);syncdir(dest.parent)
 finally:tmp.unlink(missing_ok=True)
 print(json.dumps({'output':str(dest),'policy_sha256':result['policy_sha256'],'counts':result['counts'],'application_authority':False}))
