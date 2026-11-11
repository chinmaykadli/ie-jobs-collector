"""Copy-only operator recovery. Default inspect; never guesses a commit.
An operator chooses an exact generation ID. Publishing a recovered snapshot may
re-expose old leads, so downstream consumers must deduplicate by stable job keys.
"""
import pathlib,json,os,argparse,hashlib
from generation_runner import writer,verify_generation,syncdir,current

def inspect(root):
 root=pathlib.Path(root);result=[]
 try:active=current(root)
 except Exception:active=None
 for folder in ['generations','superseded']:
  for p in (root/folder).iterdir()if(root/folder).exists()else[]:
   try:
    verify_generation(p);m=json.loads((p/'manifest.json').read_text());result.append({'generation':p.name,'seq':m['seq'],'parent':m['parent'],'integrity':'PASS','folder':folder,'current':p.resolve()==active})
   except Exception as e:result.append({'generation':p.name,'integrity':'FAIL','error':type(e).__name__,'folder':folder,'current':p.resolve()==active})
 return sorted(result,key=lambda x:x.get('seq',-1))
def recover(root,chosen):
 root=pathlib.Path(root)
 if pathlib.Path(chosen).name!=chosen:raise ValueError('Exact generation name required')
 with writer(root):
  p=root/'generations'/chosen
  if not p.exists():
   previous=root/'superseded'/chosen;verify_generation(previous);previous.chmod(0o700);previous.rename(p);syncdir(root/'superseded');syncdir(root/'generations')
  verify_generation(p);p.chmod(0o555);before=os.readlink(root/'current')if(root/'current').is_symlink()else None
  link=root/'.next-recovery';link.unlink(missing_ok=True);link.symlink_to(pathlib.Path('generations')/chosen);os.replace(link,root/'current');syncdir(root)
  return {'recovered_generation':current(root).name,'prior_pointer':before,'consumer_replay_possible':True}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('root');parser.add_argument('--commit-generation');args=parser.parse_args()
 print(json.dumps(recover(args.root,args.commit_generation)if args.commit_generation else inspect(args.root),indent=2))
