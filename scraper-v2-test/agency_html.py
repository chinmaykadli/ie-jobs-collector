"""Explicit site adapters only. Never infer a job location from site-wide text."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
class Scoped(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.parts={'title':[],'location':[],'description':[]};self.matches={k:0 for k in self.parts}
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs);classes=set((attrs.get('class')or'').split());field=None
  if tag=='div'and'job'in classes and'type-job'in classes and str(attrs.get('id','')).startswith('post-'):field='job_container'
  elif tag=='h1'and'entry-title'in classes and any(f=='job_container'for _,f in self.stack):field='title'
  elif tag=='span'and'loc'in classes and any(f=='job_container'for _,f in self.stack):field='location'
  elif tag=='div'and'entry-content'in classes and any(f=='job_container'for _,f in self.stack):field='description'
  if field in self.matches:self.matches[field]+=1
  if tag not in('br','img','hr','input','meta','link','wbr','source'):self.stack.append((tag,field))
  if tag in('br','p','li'):
   for _,f in self.stack:
    if f in self.parts:self.parts[f].append(' ')
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs);self.handle_endtag(tag)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,-1,-1):
   if self.stack[i][0]==tag:del self.stack[i:];break
 def handle_data(self,data):
  if any(tag in('script','style')for tag,_ in self.stack):return
  for _,field in self.stack:
   if field in self.parts:self.parts[field].append(data)
def extract(source,url,text):
 if source!='redchairrecruitment.ie'or urlsplit(url).hostname not in(source,'www.'+source)or not urlsplit(url).path.startswith('/job/'):return None
 parser=Scoped();parser.feed(text)
 if any(parser.matches[k]!=1 for k in parser.matches):return None
 title=' '.join(''.join(parser.parts['title']).split());location=' '.join(''.join(parser.parts['location']).split());description=' '.join(''.join(parser.parts['description']).split())
 if not location.lower().startswith('location:')or not title or not description:return None
 location=location.split(':',1)[1].strip(' ,')
 if not location:return None
 return {'@type':'JobPosting','title':title,'description':description,'jobLocation':{'address':{'addressLocality':location}},'_evidence':'EXPLICIT_JOB_FIELD'}
