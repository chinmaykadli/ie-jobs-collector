"""Strict copy-only display policy. No inferred company windows.
Agency rows are excluded until separately verified employer identity exists.
An explicit empty list is valid only when its digest is approved externally.
"""
import hashlib,json,unicodedata,re
KEYS={'verified','blocked_companies'}
def clean(value,maxlen=300):
 if not isinstance(value,str):return ''
 value=''.join(c for c in unicodedata.normalize('NFKC',value)if unicodedata.category(c)not in ('Cf','Cc'))
 return re.sub(r'\s+',' ',value).strip()[:maxlen]
def company(value):
 value=clean(value,500).casefold();value=re.sub(r'[^\w\s]',' ',value);value=re.sub(r'\s+',' ',value).strip()
 while True:
  new=re.sub(r'\s+(limited|ltd|inc|incorporated|llc|plc|corp|corporation)$','',value)
  if new==value:return value
  value=new

def validate(policy):
 if not isinstance(policy,dict)or set(policy)!=KEYS or policy.get('verified')is not True:return None
 names=policy.get('blocked_companies')
 if not isinstance(names,list)or any(not isinstance(x,str)or not clean(x)for x in names):return None
 digest=hashlib.sha256(json.dumps(policy,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()).hexdigest()
 return {'blocked':{company(x)for x in names},'sha256':digest}

def load_policy(text):
 def pairs(items):
  result={}
  for k,v in items:
   if k in result:raise ValueError('Duplicate policy key')
   result[k]=v
  return result
 return json.loads(text,object_pairs_hook=pairs)

def pinned(policy,expected):
 checked=validate(policy)
 if not checked or not isinstance(expected,str)or checked['sha256']!=expected:raise ValueError('Approved policy digest mismatch')
 return checked
