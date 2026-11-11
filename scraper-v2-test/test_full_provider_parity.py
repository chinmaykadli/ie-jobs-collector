"""Offline all-configured-source SQLite parity. No network or production writes."""
import json,pathlib,tempfile,unittest,copy
from unittest.mock import patch
from test_sqlite_parity import FixedDate,clean,original
import ingest,ats_extra
SOURCES=json.load(open('sources.json'))
def make(s,rev=0):
 a=s['ats'];id='fixture-1';title='Operations Analyst'+(' Updated'if rev else '');u='https://example.invalid/job/fixture-1';desc='Duties and requirements. '*50
 if a=='greenhouse':return {'jobs':[dict(id=id,title=title,location={'name':'Dublin, Ireland'},content=desc,absolute_url=u)],'meta':{'total':1}}
 if a=='lever':return [dict(id=id,text=title,categories={'location':'Dublin, Ireland'},descriptionPlain=desc,hostedUrl=u)]
 if a=='ashby':return {'jobs':[dict(id=id,title=title,location='Dublin, Ireland',descriptionPlain=desc,jobUrl=u)]}
 if a=='smartrecruiters':return {'content':[dict(id=id,name=title,location={'city':'Dublin','country':'ie'})],'totalFound':1}
 if a=='workable':return {'jobs':[dict(id=id,title=title,city='Dublin',country='Ireland',description=desc,url=u)]}
 if a=='recruitee':return {'offers':[dict(id=id,title=title,location='Dublin, Ireland',description=desc,careers_url=u)]}
 if a=='workday':return {'jobs':[dict(bulletFields=[id],title=title,locationsText='Dublin, Ireland',externalPath='/job/Dublin/fixture-1')],'complete':True}
 if a=='gem':return [dict(id=id,title=title,location={'name':'Dublin, Ireland'},content_plain=desc,absolute_url=u)]
 if a=='rippling':return [dict(uuid=id,name=title,workLocation={'label':'Dublin, Ireland'},url=u)]
 raise AssertionError(a)
def empty(s):
 p=make(s)
 if isinstance(p,list):return []
 for k,v in p.items():
  if isinstance(v,list):p[k]=[]
 for k in ['totalFound']:
  if k in p:p[k]=0
 if 'meta'in p:p['meta']['total']=0
 return p
class FullParity(unittest.TestCase):
 def test_every_configured_source_lifecycle(self):
  self.assertEqual(len(SOURCES),135)
  for s in SOURCES:
   with self.subTest(source=s['ats']+':'+s['token']),tempfile.TemporaryDirectory()as d:
    a=pathlib.Path(d)/'json';b=pathlib.Path(d)/'sqlite'
    with patch.object(ingest,'datetime',FixedDate),patch.object(ingest,'desc_enricher',None):
     def fail(_):raise ValueError('simulated upstream outage')
     for label,fetch in [('cold',lambda _:make(s)),('same',lambda _:make(s)),('edit',lambda _:make(s,1)),('error',fail),('recover',lambda _:make(s,1)),('empty',lambda _:empty(s)),('reappear',lambda _:make(s))]:
      original([s],a,fetcher=fetch);ingest.ingest([s],b,fetcher=fetch)
      for f in ['state.json','health.json','last-changes.json','raw-irish-queue.json']:
       self.assertEqual(clean(json.loads((a/f).read_text())),clean(json.loads((b/f).read_text())),(s['token'],label,f))
if __name__=='__main__':unittest.main()
