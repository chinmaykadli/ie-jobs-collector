import unittest,json
from agency_cycle import crawl,cycle,source_url
class AgencyCycle(unittest.TestCase):
 def test_all_29_source_configs_traverse_and_reject_foreign_urls(self):
  for s in json.load(open('agency_sources.json')):
   with self.subTest(s=s['domain']):
    host=s['domain'];u='https://'+host+'/jobs/operations-coordinator-123'
    feed='<urlset><url><loc>'+u+'</loc></url></urlset>'
    urls,h=crawl(s,lambda _:feed);self.assertEqual(urls,[u]);self.assertTrue(h['complete'])
    for hostile in ['file:///etc/passwd','https://127.0.0.1/job','https://evil.invalid/jobs/role','http://'+host+'/jobs/role','https://'+host+'@evil.invalid/job']:
     with self.assertRaises(ValueError):source_url(hostile,host)
 def test_incomplete_sitemap_never_marks_absence_and_entities_fail(self):
  s={'domain':'example.invalid','sitemaps':['https://example.invalid/sitemap.xml']}
  urls,h=crawl(s,lambda _:'<!DOCTYPE x [<!ENTITY y "secret">]><urlset/>');self.assertFalse(h['complete'])
  state={'jobs':{'https://example.invalid/jobs/existing':{'availability':'LISTED','checked_at':1}}}
  def fail(_):raise ValueError('transport error')
  new,h=cycle(s,state,fail,now=10);self.assertEqual(next(iter(new['jobs'].values()))['availability'],'LISTED')
if __name__=='__main__':unittest.main()
