import json,pathlib,tempfile,unittest
from unittest.mock import patch
import ingest,ats_extra
S={'ats':'workday','token':'accenture','company':'Accenture','url':'https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs'}
def job(i):return {'title':'Operations Analyst','bulletFields':[str(i),'Dublin'],'locationsText':'Dublin, Ireland','externalPath':'/job/Dublin/Analyst_'+str(i)}
def payload(rows):return {'jobs':rows,'complete':True,'total':len(rows)}

class SkeletalRecordTest(unittest.TestCase):
    def run_feed(self,d,rows):
        with patch.object(ingest,'desc_enricher',None):return ingest.ingest([S],d,fetcher=lambda _:payload(rows))
    def test_skeletal_location_recovered_in_evidence(self):
        v=ats_extra.normalize(S,payload([{'bulletFields':['R00325027','Dublin']}]))
        self.assertEqual(len(v),0)
        rec=v.quarantined_records[0]
        self.assertEqual(rec['id'],'R00325027')
        self.assertEqual(rec['reason'],'Job missing title')
        self.assertEqual(rec['record_class'],'SKELETAL_NO_TITLE_NO_PATH')
        self.assertEqual(rec['recovered_location'],'Dublin')
    def test_partial_record_keeps_plain_reason(self):
        # title missing but owning path present: not a skeletal record
        v=ats_extra.normalize(S,payload([{'bulletFields':['R1','Dublin'],'externalPath':'/job/Dublin/X_R1'}]))
        self.assertEqual(v.quarantined_records[0],{'id':'R1','reason':'Job missing title'})
    def test_full_record_unaffected(self):
        v=ats_extra.normalize(S,payload([job('1')]))
        self.assertEqual(len(v),1);self.assertEqual(v[0]['location'],'Dublin, Ireland')
        self.assertEqual(v.quarantined_records,[])
    def test_locations_text_wins_over_bulletfields(self):
        j=job('1');v=ats_extra.normalize(S,payload([j]))
        self.assertEqual(v[0]['location'],'Dublin, Ireland')
    def test_ingest_receipt_carries_record_class(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.run_feed(d,[job('1'),{'bulletFields':['R00325027','Dublin']}])
            r=h['source_health'][0]
            self.assertEqual(r['status'],'DEGRADED_PARTIAL')
            q=r['quarantined_records'][0]
            self.assertEqual(q['record_class'],'SKELETAL_NO_TITLE_NO_PATH')
            self.assertEqual(q['recovered_location'],'Dublin')

if __name__=='__main__': unittest.main()
