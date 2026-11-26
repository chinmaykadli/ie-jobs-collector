import json,pathlib,tempfile,unittest
import ingest,ats_extra
from ats_extra import full_list_pagination, pagination_proof

def ashby_payload(n):
    return {'jobs':[{'id':'id-%d'%i,'title':'Analyst %d'%i,'jobUrl':'https://jobs.ashbyhq.com/x/%d'%i,'location':'Dublin','descriptionPlain':'ops analyst'} for i in range(n)],'apiVersion':1}
def lever_payload(n):
    return [{'id':'id-%d'%i,'text':'Analyst %d'%i,'hostedUrl':'https://jobs.lever.co/x/%d'%i,'categories':{'location':'Dublin'},'lists':[]} for i in range(n)]
def workable_payload(n):
    return {'name':'Crown','jobs':[{'shortcode':'SC%d'%i,'title':'Analyst %d'%i,'url':'https://apply.workable.com/x/j/%d'%i,'country':'IE'} for i in range(n)]}

class FullListProofTest(unittest.TestCase):
    def test_ashby_complete_with_proof(self):
        state,proof=full_list_pagination(ashby_payload(12),{'ats':'ashby'})
        self.assertEqual(state,'COMPLETE_EXPLICIT')
        self.assertEqual(proof['method'],'PROVIDER_FULL_LIST_CONTRACT')
        self.assertEqual(proof['rows'],12);self.assertEqual(proof['distinct_stable_ids'],12)
        self.assertFalse(proof['continuation_fields_present'])
    def test_lever_and_workable_complete(self):
        self.assertEqual(full_list_pagination(lever_payload(22),{'ats':'lever'})[0],'COMPLETE_EXPLICIT')
        self.assertEqual(full_list_pagination(workable_payload(23),{'ats':'workable'})[0],'COMPLETE_EXPLICIT')
    def test_empty_list_is_genuine_zero(self):
        self.assertEqual(full_list_pagination([],{'ats':'gem'})[0],'COMPLETE_EXPLICIT')
        self.assertEqual(full_list_pagination([],{'ats':'rippling'})[0],'COMPLETE_EXPLICIT')
    def test_continuation_metadata_fails_closed(self):
        p=ashby_payload(3);p['hasMore']=True
        self.assertEqual(full_list_pagination(p,{'ats':'ashby'})[0],'INCOMPLETE')
        p=ashby_payload(3);p['nextCursor']='abc'
        self.assertEqual(full_list_pagination(p,{'ats':'ashby'})[0],'INCOMPLETE')
    def test_duplicate_ids_not_complete(self):
        p=ashby_payload(3);p['jobs'][1]['id']=p['jobs'][0]['id']
        self.assertEqual(full_list_pagination(p,{'ats':'ashby'})[0],'INCOMPLETE')
    def test_missing_id_not_complete(self):
        p=lever_payload(3);del p[1]['id']
        self.assertEqual(full_list_pagination(p,{'ats':'lever'})[0],'INCOMPLETE')
    def test_unexpected_envelope_not_verified(self):
        self.assertEqual(full_list_pagination({'unexpected':1},{'ats':'ashby'})[0],'NOT_VERIFIED')
        self.assertEqual(full_list_pagination({'jobs':'notalist'},{'ats':'workable'})[0],'NOT_VERIFIED')
        self.assertEqual(full_list_pagination({'jobs':[]},{'ats':'lever'})[0],'NOT_VERIFIED')
    def test_other_providers_untouched(self):
        self.assertEqual(full_list_pagination({'jobs':[]},{'ats':'greenhouse'}),(None,None))
    def test_evidence_and_receipt_integration(self):
        S={'ats':'ashby','token':'t','company':'T','url':'https://api.ashbyhq.com/posting-api/job-board/t'}
        p=ashby_payload(4)
        for j in p['jobs']: j.update(publishedAt='2026-01-01T00:00:00Z')
        with unittest.mock.patch.object(ingest,'desc_enricher',None):
            with tempfile.TemporaryDirectory() as d:
                h=ingest.ingest([S],d,fetcher=lambda _:p)
        r=h['source_health'][0]
        self.assertEqual(r['pagination_state'],'COMPLETE_EXPLICIT')
        self.assertEqual(r['pagination_proof']['rows'],4)
        self.assertNotIn('ashby:t',h['pagination_unverified_sources'])
    def test_proof_none_when_not_complete(self):
        self.assertIsNone(pagination_proof([],{'ats':'gem'},'INCOMPLETE'))
        self.assertIsNone(pagination_proof({}, {'ats':'greenhouse'},'COMPLETE_EXPLICIT'))

import unittest.mock
if __name__=='__main__': unittest.main()
