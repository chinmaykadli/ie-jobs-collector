import unittest
import ingest
import ats_extra

class MultiLocationTest(unittest.TestCase):
    def record(self, location, ats='rippling'):
        return dict(key='rippling:test:1', ats=ats, location=location, irish_location_match='Dublin' in location, remote_ireland_eligibility_unverified=False, context_candidate=True)
    def test_reordered_locations_are_not_change(self):
        a=self.record('Dublin; Cork'); b=self.record('Cork; Dublin')
        self.assertEqual(ingest.changed_fields(a,b), [])
    def test_addition_and_removal_remain_change(self):
        for loc in ['Dublin', 'Dublin; Cork; Galway']:
            self.assertIn('location', ingest.changed_fields(self.record('Dublin; Cork'),self.record(loc)))
    def test_title_change_still_detected(self):
        a=self.record('Dublin; Cork') | {'title':'Analyst'}
        b=self.record('Cork; Dublin') | {'title':'Senior Analyst'}
        self.assertEqual(ingest.changed_fields(a,b), ['title'])
    def test_does_not_change_other_board_semantics(self):
        self.assertIn('location', ingest.changed_fields(self.record('Dublin; Cork','greenhouse'),self.record('Cork; Dublin','greenhouse')))
    def test_merge_preserves_locations_and_irish_match(self):
        a=self.record('Cork'); b=self.record('Dublin'); c=self.record('Cork')
        for rows in [[a,b,c],[b,c,a]]:
            merged=ats_extra._merge_dupes([dict(r) for r in rows])
            self.assertEqual(len(merged),1)
            self.assertEqual(merged[0]['location'],'Cork; Dublin')
            self.assertTrue(merged[0]['irish_location_match'])
    def test_workable_order_only(self):
        self.assertEqual(ingest.changed_fields(self.record('Dublin; Cork','workable'),self.record('Cork; Dublin','workable')),[])
    def test_foreign_dublin_not_newly_irish(self):
        self.assertFalse(ingest.irish_location('Dublin, OH; Cleveland, OH'))
        self.assertTrue(ingest.irish_location('Dublin, Ireland; Cleveland, OH'))

if __name__=='__main__': unittest.main()
