import unittest
from desc_fetch import detail_url
class WorkdayTenantTests(unittest.TestCase):
 def test_composite_tenant_site(self):
  self.assertEqual(detail_url('workday','workday:jll__jllcareers:R1','https://jll.wd1.myworkdayjobs.com/jllcareers/job/Dublin/Helpdesk_R1','https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs'),'https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/job/Dublin/Helpdesk_R1')
 def test_locale_and_no_composite_fallback(self):
  self.assertEqual(detail_url('workday','workday:jll__jllcareers:R1','https://jll.wd1.myworkdayjobs.com/en-US/jllcareers/job/Dublin/Helpdesk_R1','https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs'),'https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/job/Dublin/Helpdesk_R1')
  self.assertIsNone(detail_url('workday','workday:jll__jllcareers:R1','https://jll.wd1.myworkdayjobs.com/jllcareers/job/Dublin/Helpdesk_R1'))
 def test_host_site_scheme_mismatch_fail_closed(self):
  u='https://jll.wd1.myworkdayjobs.com/jllcareers/job/Dublin/Helpdesk_R1'
  for s in ['https://other.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs','https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/different/jobs','http://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs']:
   self.assertIsNone(detail_url('workday','workday:jll__jllcareers:R1',u,s))
if __name__=='__main__':unittest.main()
