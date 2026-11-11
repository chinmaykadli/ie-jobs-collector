import unittest,copy,hashlib
from review_policy import assess,build_digest,validate,jd_sha256
from screen_policy import validate as validate_screen
SCREEN={"verified":True,"blocked_companies":[]}
SCREEN_HASH=validate_screen(SCREEN)["sha256"]
class PolicyTests(unittest.TestCase):
 def setUp(self):
  self.p={'schema':2,'provenance':['rulebook-live-20261111'],'applications':[],'company_exceptions':[],'reviewed_jobs':[],'hide_companies':[]}
  self.j={'key':'ashby:harvey:x','company':'Harvey','title':'Generalist','job_url':'https://jobs.ashbyhq.com/harvey/req','description':'own JD','description_state':'PRESENT','description_freshness':'LIVE_FEED','irish_location_match':True,'active':True,'stale':False}
 def review(self):self.p['reviewed_jobs']=[{'url':self.j['job_url'],'decision':'REVIEWED_MATCH','jd_sha256':jd_sha256(self.j),'evidence':'full-JD-review-source'}]
 def test_unreviewed_never_qualified(self):
  r=assess(self.j,self.p);self.assertEqual(r['qualification_state'],'NOT_ASSESSED');self.assertFalse(r['application_authority'])
 def test_company_history_not_hidden_or_exact_dedupe(self):
  self.p['applications']=[{'company':'HARVEY Inc.','url':'https://jobs.ashbyhq.com/harvey/other','evidence':'app146'}];r=assess(self.j,self.p);self.assertTrue(r['visible']);self.assertIn('PRIOR_COMPANY_REQUIRES_OWNER_EXCEPTION',r['reasons']);self.assertEqual(r['state'],'NEEDS_REVIEW')
 def test_exact_req_dedupe(self):
  self.p['applications']=[{'company':'Harvey','url':self.j['job_url'],'evidence':'receipt'}];self.assertEqual(assess(self.j,self.p)['state'],'ALREADY_APPLIED')
 def test_exact_exception_not_blanket(self):
  self.p['applications']=[{'company':'Harvey','evidence':'app146'}];self.p['company_exceptions']=[{'company':'Harvey','url':'https://jobs.ashbyhq.com/harvey/different','owner_evidence':'yes-message'}];self.assertIn('PRIOR_COMPANY_REQUIRES_OWNER_EXCEPTION',assess(self.j,self.p)['reasons'])
 def test_exact_review_is_required_and_not_authority(self):
  self.review();r=assess(self.j,self.p);self.assertEqual(r['state'],'REVIEWED_MATCH');self.assertFalse(r['application_authority']);self.j['description']='changed';self.assertEqual(assess(self.j,self.p)['state'],'NEEDS_REVIEW')
 def test_stale_remote_missing_jd_fail_closed(self):
  self.review()
  for k,v in [('stale',True),('irish_location_match',False),('description_state','MISSING'),('description_freshness','STALE_CACHE'),('remote_ireland_eligibility_unverified',True),('active',False)]:
   j=copy.deepcopy(self.j);j[k]=v;self.assertEqual(assess(j,self.p)['state'],'NEEDS_REVIEW')
 def test_hide_needs_owner_evidence(self):
  self.p['hide_companies']=[{'company':'Harvey'}]
  with self.assertRaises(ValueError):validate(self.p)
 def test_deterministic_digest(self):self.assertEqual(build_digest([self.j],self.p,validate(self.p),SCREEN,SCREEN_HASH),build_digest([self.j],self.p,validate(self.p),SCREEN,SCREEN_HASH))
 def test_digest_filters_agency_and_explicit_owner_hide(self):
  j=copy.deepcopy(self.j);j['ats']='agency';self.assertEqual(build_digest([j],self.p,validate(self.p),SCREEN,SCREEN_HASH)['jobs'],[])
  self.p['hide_companies']=[{'company':'Harvey','owner_evidence':'owner-message'}];self.assertEqual(build_digest([self.j],self.p,validate(self.p),SCREEN,SCREEN_HASH)['jobs'],[])
 def test_tracking_default_port_and_application_suffix_dedupe(self):
  self.p['applications']=[{'company':'Harvey','url':'https://jobs.ashbyhq.com:443/harvey/req/application?utm_source=x','evidence':'receipt'}];self.assertEqual(assess(self.j,self.p)['state'],'ALREADY_APPLIED')
 def test_title_change_invalidates_review(self):
  self.review();self.j['title']='different';self.assertIn('JD_CHANGED_SINCE_REVIEW',assess(self.j,self.p)['reasons'])
 def test_source_contract_and_pin(self):
  with self.assertRaises(ValueError):build_digest([self.j],self.p)
  with self.assertRaises(ValueError):build_digest([{'title':'UIprojection'}],self.p,validate(self.p),SCREEN,SCREEN_HASH)
 def test_duplicate_canonical_review_refused(self):
  self.review();self.p['reviewed_jobs']*=2
  with self.assertRaises(ValueError):validate(self.p)
 def test_strict_duplicate_key_loader(self):
  from screen_policy import load_policy
  with self.assertRaises(ValueError):load_policy('{"schema":2,"schema":2}')
 def test_pinned_display_block_does_not_reappear(self):
  screen={'verified':True,'blocked_companies':['Harvey']};self.assertEqual(build_digest([self.j],self.p,validate(self.p),screen,validate_screen(screen)['sha256'])['jobs'],[])
 def test_missing_or_wrong_screen_pin_fail_closed(self):
  with self.assertRaises(ValueError):build_digest([self.j],self.p,validate(self.p))
  with self.assertRaises(ValueError):build_digest([self.j],self.p,validate(self.p),SCREEN,'wrong')
if __name__=='__main__':unittest.main()
