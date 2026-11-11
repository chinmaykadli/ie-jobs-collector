import unittest,json,io
from unittest.mock import patch
import ats_extra,bounded_http
class Resp(io.BytesIO):
 def getcode(self):return 200
class Paging(unittest.TestCase):
 def run_pages(self,pages,max_pages=15):
  calls=[]
  def fetch(req,**kwargs):
   body=json.loads(req.data);calls.append(body['offset']);return Resp(json.dumps(pages[len(calls)-1]).encode())
  with patch.object(bounded_http,'urlopen',fetch):result=ats_extra.workday_pull('https://example.invalid/wday/cxs/tenant/site/jobs',max_pages=max_pages)
  return result,calls
 def rows(self,start,n):return [{'externalPath':'/job/'+str(i),'bulletFields':[str(i)],'title':'Role'}for i in range(start,start+n)]
 def test_known_total_full_pages(self):
  r,c=self.run_pages([{'total':21,'jobPostings':self.rows(0,20)},{'total':21,'jobPostings':self.rows(20,1)}]);self.assertTrue(r['complete']);self.assertEqual(c,[0,20]);self.assertEqual(len(r['jobs']),21)
 def test_later_zero_and_omitted_total(self):
  for end in [{'total':0,'jobPostings':self.rows(20,1)},{'jobPostings':self.rows(20,1)}]:
   r,c=self.run_pages([{'total':21,'jobPostings':self.rows(0,20)},end]);self.assertTrue(r['complete']);self.assertEqual(r['total'],21)
 def test_repeated_page_and_total_drift_rejected(self):
  for pages in [[{'total':40,'jobPostings':self.rows(0,20)},{'total':40,'jobPostings':self.rows(0,20)}],[{'total':21,'jobPostings':self.rows(0,20)},{'total':20,'jobPostings':self.rows(20,1)}]]:
   with self.assertRaises(ValueError):self.run_pages(pages)
 def test_invalid_total_refused(self):
  for value in [True,-1,'20',None]:
   with self.assertRaises(ValueError):self.run_pages([{'total':value,'jobPostings':[]}])
 def test_short_page_and_cap(self):
  r,c=self.run_pages([{'jobPostings':self.rows(0,2)}]);self.assertFalse(r['complete'])
  r,c=self.run_pages([{'jobPostings':self.rows(0,20)}],max_pages=1);self.assertFalse(r['complete'])
  r,c=self.run_pages([{'total':21,'jobPostings':self.rows(0,20)}],max_pages=1);self.assertFalse(r['complete'])
 def test_failed_later_page_raises(self):
  count=[0]
  def fetch(*a,**k):
   count[0]+=1
   if count[0]==2:raise TimeoutError('second page')
   return Resp(json.dumps({'total':21,'jobPostings':self.rows(0,20)}).encode())
  with patch.object(bounded_http,'urlopen',fetch),self.assertRaises(TimeoutError):ats_extra.workday_pull('https://example.invalid/wday/cxs/tenant/site/jobs')
if __name__=='__main__':unittest.main()
