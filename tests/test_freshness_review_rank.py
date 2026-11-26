import json,pathlib,tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import ingest,ats_extra,ranking

GH={'ats':'greenhouse','token':'t','company':'T','url':'https://boards.greenhouse.io/t'}
def ghjob(i,title='Operations Analyst',loc='Dublin, Ireland',desc='operations analyst role'):
    return {'id':str(i),'title':title,'location':{'name':loc},'content':desc,'absolute_url':'https://job-boards.greenhouse.io/t/jobs/%s'%i,'updated_at':'2026-01-01T00:00:00Z'}
def payload(rows):return {'jobs':rows,'meta':{'total':len(rows)}}

class FreshnessTest(unittest.TestCase):
    def run_feed(self,d,rows):
        with patch.object(ingest,'desc_enricher',None):return ingest.ingest([GH],d,fetcher=lambda _:payload(rows))
    def test_run_id_and_fresh_until(self):
        with tempfile.TemporaryDirectory() as d:
            h1=self.run_feed(d,[ghjob(1)]);h2=self.run_feed(d,[ghjob(1)])
        self.assertNotEqual(h1['run_id'],h2['run_id'])
        checked=datetime.fromisoformat(h1['checked_at']);fresh=datetime.fromisoformat(h1['fresh_until'])
        self.assertEqual((fresh-checked).total_seconds(),5400)
        self.assertEqual(h1['expected_interval_seconds'],3600)
        self.assertIn('stale',h1['freshness_rule'])
        self.assertEqual(h1['source_receipt_schema_version'],3)

class ReviewPersistenceTest(unittest.TestCase):
    def run_feed(self,d,rows):
        with patch.object(ingest,'desc_enricher',None):return ingest.ingest([GH],d,fetcher=lambda _:payload(rows))
    def test_review_survives_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_feed(d,[ghjob(1)])
            p=pathlib.Path(d)/'state.json';state=json.loads(p.read_text())
            r=state['jobs']['greenhouse:t:1'];r['review_state']='VERIFIED_FIT';r['reviewed_at']='2026-11-26T00:00:00+00:00'
            p.write_text(json.dumps(state))
            h=self.run_feed(d,[ghjob(1)])
            state=json.loads(p.read_text())
            self.assertEqual(state['jobs']['greenhouse:t:1']['review_state'],'VERIFIED_FIT')
            self.assertEqual(h['fit_counts']['verified_fit'],1)
            self.assertEqual(h['fit_counts']['not_reviewed'],0)
    def test_description_change_invalidates_review(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_feed(d,[ghjob(1)])
            p=pathlib.Path(d)/'state.json';state=json.loads(p.read_text())
            state['jobs']['greenhouse:t:1']['review_state']='VERIFIED_FIT';p.write_text(json.dumps(state))
            self.run_feed(d,[ghjob(1,desc='completely new description text')])
            state=json.loads(p.read_text())
            r=state['jobs']['greenhouse:t:1']
            self.assertEqual(r['review_state'],'NOT_REVIEWED')
            self.assertEqual(r['review_invalidated_reason'],'description_changed')
    def test_backlog_age(self):
        with tempfile.TemporaryDirectory() as d:
            h=self.run_feed(d,[ghjob(1),ghjob(2,'Other Role')])
            self.assertEqual(h['review_backlog']['unreviewed_count'],2)
            self.assertEqual(h['review_backlog']['oldest_unreviewed_age_days'],0)

class RemoteQueueTest(unittest.TestCase):
    def test_remote_pending_queued_not_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(ingest,'desc_enricher',None):
                h=ingest.ingest([GH],d,fetcher=lambda _:payload([ghjob(1),ghjob(2,'Analyst Remote','Remote - EMEA')]))
            q=json.loads((pathlib.Path(d)/'raw-irish-queue.json').read_text())
        self.assertEqual(len(q),2)
        remote=[j for j in q if j['key']=='greenhouse:t:2'][0]
        self.assertEqual(remote['eligibility_review_state'],'REMOTE_COUNTRY_REVIEW_PENDING')
        self.assertEqual(remote['rank_tier'],'REMOTE_COUNTRY_REVIEW')
        irish=[j for j in q if j['key']=='greenhouse:t:1'][0]
        self.assertEqual(irish['eligibility_review_state'],'IRELAND_LOCATION_MATCHED')
        self.assertEqual(h['fit_counts']['remote_country_review_pending'],1)
        self.assertEqual(h['irish_active_raw'],1)

class DeadlineTest(unittest.TestCase):
    today=datetime(2026,11,26,tzinfo=timezone.utc).date()
    def parse(self,text):return ranking.parse_deadline(text,self.today)
    def test_formats(self):
        self.assertEqual(self.parse('Closing date: 15 December 2026. Apply now')[0],'2026-12-15')
        self.assertEqual(self.parse('Apply by December 15, 2026')[0],'2026-12-15')
        self.assertEqual(self.parse('applications close 2026-12-15')[0],'2026-12-15')
        self.assertEqual(self.parse('Closing date 15/12/2026')[0],'2026-12-15')
        self.assertEqual(self.parse('Closing Date: 4th January 2027')[0],'2027-01-04')
    def test_no_cue_no_deadline(self):
        self.assertEqual(self.parse('This role starts 15 December 2026 in our office')[0],None)
        self.assertEqual(self.parse('We were founded in 2015 and grew 15/12/2026 style')[0],None)
    def test_past_and_far_future_rejected(self):
        self.assertEqual(self.parse('Closing date: 1 January 2026')[0],None)
        self.assertEqual(self.parse('Closing date: 1 January 2035')[0],None)
    def test_snippet_kept(self):
        iso,snip=self.parse('Closing date: 15 December 2026 for this role.')
        self.assertIn('15 December 2026',snip)

class RankOrderTest(unittest.TestCase):
    today=datetime(2026,11,26,tzinfo=timezone.utc).date()
    def job(self,key,ctx,desc='',changed='2026-11-20T00:00:00+00:00',review='NOT_REVIEWED',irish=True):
        return {'key':key,'company':'C','title':'T'+key,'context_candidate':ctx,'description':desc,
                'last_changed_at':changed,'first_seen_at':changed,'review_state':review,
                'irish_location_match':irish,'remote_ireland_eligibility_unverified':not irish}
    def test_order(self):
        deadline_soon=self.job('a',True,'Closing date: 1 December 2026')
        deadline_later=self.job('b',True,'Closing date: 20 December 2026')
        fresh=self.job('c',True,changed='2026-11-26T00:00:00+00:00')
        stale=self.job('d',True,changed='2026-11-01T00:00:00+00:00')
        raw=self.job('e',False)
        verified=self.job('f',False,review='VERIFIED_FIT')
        remote=self.job('g',True,irish=False)
        out=ranking.rank_queue([stale,raw,deadline_later,fresh,deadline_soon,verified,remote],self.today)
        order=[j['key'] for j in out]
        self.assertEqual(order,['f','a','b','c','d','g','e'])
        self.assertEqual([j['queue_rank'] for j in out],[1,2,3,4,5,6,7])
        self.assertEqual(out[1]['application_deadline'],'2026-12-01')

if __name__=='__main__': unittest.main()
