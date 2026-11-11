"""Copy-only policy republish without network. Keeps original source observation time.
Caller must pin a separately approved policy digest. No fresh-data claim.
"""
import pathlib,json,shutil,argparse
from generation_runner import writer,current,verify_generation,run
from screen_policy import pinned,load_policy

def regenerate(root,policy,expected):
 pinned(policy,expected);root=pathlib.Path(root)
 # run acquires the writer before selecting current, so copy its backup's sibling outputs
 def outputs(sources,stage,fetcher=None):
  old=current(root);verify_generation(old)
  for name in ['state.json','health.json','raw-irish-queue.json']:shutil.copyfile(old/name,stage/name)
  (stage/'last-changes.json').write_text('[]');(stage/'changes.jsonl').write_text('')
  return {'display_only':True}
 return run(root,[],outputs,policy=policy)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('policy');p.add_argument('--policy-sha256',required=True);a=p.parse_args();print(json.dumps(regenerate(a.root,load_policy(pathlib.Path(a.policy).read_text()),a.policy_sha256)))
