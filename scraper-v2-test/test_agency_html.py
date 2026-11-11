import unittest
from agency_safe import parse_page
class HTML(unittest.TestCase):
 def test_scoped_location_not_footer(self):
  text='<div id="post-1" class="job type-job"><h1 class="entry-title">Operations support</h1><span class="loc">Location: <span>London, UK</span></span><div class="entry-content"><p>Full job content.</p></div><footer>Dublin Ireland office</footer></div>'
  row=parse_page('redchairrecruitment.ie','https://redchairrecruitment.ie/job/1/',text);self.assertFalse(row['irish_location_match']);self.assertEqual(row['description'],'Full job content.');self.assertNotIn('footer',row['description']);self.assertEqual(row['location_state'],'EXPLICIT_JOB_FIELD')
  row=parse_page('redchairrecruitment.ie','https://redchairrecruitment.ie/job/1/',text.replace('London, UK','Ireland'));self.assertTrue(row['irish_location_match'])
 def test_no_job_field_no_match(self):
  row=parse_page('redchairrecruitment.ie','https://redchairrecruitment.ie/job/1/','<h1 class="entry-title">Example</h1><div class="entry-content">Text</div><footer>Ireland</footer></div>');self.assertFalse(row['irish_location_match'])
if __name__=='__main__':unittest.main()
