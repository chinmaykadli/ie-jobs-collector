import unittest,json,pathlib
from agency_safe import parse_page,update

def page(loc='Dublin',country='IE',desc='Detailed operations duties '*500):
 r={'@context':'https://schema.org','@type':'JobPosting','title':'Operations Coordinator','description':desc,'jobLocation':{'address':{'addressLocality':loc,'addressCountry':country}}}
 return '<script type="application/ld+json">'+json.dumps(r)+'</script><footer>Dublin Ireland Office</footer>'
class Agency(unittest.TestCase):
 def test_footer_does_not_turn_foreign_role_irish(self):
  self.assertFalse(parse_page('a','https://example.invalid/1',page('London','GB'))['irish_location_match']);self.assertFalse(parse_page('a','https://example.invalid/2','<title>Operations</title><footer>Dublin Ireland</footer>')['irish_location_match'])
 def test_full_description_not_clipped(self):
  r=parse_page('a','https://example.invalid/1',page());self.assertGreater(len(r['description']),6000);self.assertTrue(r['irish_location_match'])
 def test_every_configured_agency_same_safety(self):
  sources=json.loads(pathlib.Path('agency_sources.json').read_text());self.assertEqual(len(sources),29)
  for s in sources:
   with self.subTest(source=s['domain']):self.assertFalse(parse_page(s['domain'],'https://example.invalid/1',page('London','GB'))['irish_location_match']);self.assertTrue(parse_page(s['domain'],'https://example.invalid/1',page())['irish_location_match'])
 def test_seen_edit_is_refreshed_and_missing_not_closed(self):
  u='https://example.invalid/job/1';s,r=update({},'a',[u],True,lambda _:page(),now=100)
  s,r=update(s,'a',[u],True,lambda _:page(desc='Edited real duties'),now=90000);self.assertEqual(r['changes'][0]['kind'],'CHANGED')
  s,r=update(s,'a',[],False,lambda _:None,now=100000);self.assertEqual(s['jobs'][u]['availability'],'LISTED')
  s,r=update(s,'a',[],True,lambda _:None,now=100000);self.assertEqual(s['jobs'][u]['availability'],'NOT_IN_LATEST_SITEMAP_UNVERIFIED')
if __name__=='__main__':unittest.main()

class MoreAgency(unittest.TestCase):
 def test_reappearance_before_ttl_and_explicit_other_country(self):
  from agency_safe import update,parse_page
  u='https://example.invalid/job/1';state={'jobs':{u:{'checked_at':100,'availability':'NOT_IN_LATEST_SITEMAP_UNVERIFIED'}}}
  new,_=update(state,'example',[u],True,lambda _: (_ for _ in ()).throw(AssertionError('TTL should avoid fetch')),now=110)
  self.assertEqual(new['jobs'][u]['availability'],'LISTED')
  page='<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Example','description':'full text','jobLocation':{'address':{'addressLocality':'Dublin','addressCountry':'US'}}})+'</script>'
  self.assertFalse(parse_page('example',u,page)['irish_location_match'])
