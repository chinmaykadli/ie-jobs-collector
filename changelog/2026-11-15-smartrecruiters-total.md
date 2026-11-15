# Weekly collector review - 15 November 2026

## Verified improvement
SmartRecruiters list responses are complete only when their offset is zero and their advertised total matches both the row count and distinct stable job IDs. Contradictory continuation signals take precedence. Malformed totals, duplicate or missing IDs, nonzero/missing offsets and count mismatches fail closed. Missing total metadata remains NOT_VERIFIED. Documented numeric strings and live JSON integer counts are accepted. Other provider behavior is unchanged.

This is a reconciliation safety fix, not a new pagination loop. No extra network requests are added. Incomplete responses keep prior jobs active but stale, do not emit feed removals and do not advance last success. Genuine complete one-row and zero-row responses still reconcile normally. A feed removal is not proof a vacancy has closed.

Three public Ireland-filtered list endpoints were read once each: ServiceNow (17 records), Version1 (46) and Statkraft (3). All 66 normalized records and Irish matches are byte-for-byte equivalent as JSON objects before and after the fix. This is a three-board sample, not verification of all ten configured SmartRecruiters boards. A synthetic duplicate-page fixture with two rows for one ID and total two shows the defect: baseline emits one false removal and retains one Irish job; the fix emits zero removals and retains both prior Irish jobs as stale.

Eleven new tests cover count types, zero, offsets, duplicate/missing IDs, continuation conflicts, count mismatch, baseline preservation and real withdrawals. The existing Greenhouse cross-provider test uses valid SmartRecruiters IDs and offset rather than an invalid placeholder response. All 50 tests pass: 37 in tests/ and 13 description tests.

## Bounded source yield
Snapshot: 15 November 04:38 UTC; 135 configured boards; 2,085 active Irish raw records. The retained journal is capped at 5,000 events, from 12 November 16:38 UTC through 15 November 04:38 UTC. It is not a full-week dataset. In this sample there are 489 NEW raw events, 59 Irish, 3,827 CHANGED, 647 REMOVED_FROM_FEED and 37 REAPPEARED. Of the CHANGED events, 2,569 change only source_updated_at, 831 only description and 15 only location. These are events, not qualified roles or verified weekly outcomes.

Irish NEW by provider: Workday 24, SmartRecruiters 15, Greenhouse 12, Ashby 5, Rippling 3. Qualification remains NOT_ASSESSED, so qualified-opportunity yield cannot be derived from this store. No source is removed based on an incomplete sample or a lack of NEW events. Timestamp and URL changes remain recorded.

At this snapshot all 29 ordinary Workday boards return HTTP 200; Accenture remains partial because four provider records are quarantined. Recent Workday and Rippling failures recovered without parser changes. This review does not alter Workday behavior or implement a diagnostics patch.

## Scope, deployment and rollback
Changed files: ats_extra.py, tests/test_smartrecruiters_total.py, one fixture in tests/test_greenhouse_total.py and this changelog. No source configuration, generated snapshots/state, credentials, account settings, eligibility/location/pay rules, dashboard, workflow, careers watcher or delivery settings change. Standing feed stays off.

The dedicated code commit containing this changelog is the rollback unit: revert that commit, preserving later hourly data commits and sources.json. Re-run `python -m unittest discover -s tests -v` and `python -m unittest test_descriptions -v`. The existing push workflow is protected by its UTC-hour guard and should skip collection when that hour is already published. Confirm the workflow result and next ordinary hourly result separately; local fixtures do not prove deployment.

## Sources
- https://developers.smartrecruiters.com/reference/v1listpostings
- https://developers.smartrecruiters.com/docs/listresult
- https://developers.smartrecruiters.com/docs/posting-api
- https://api.smartrecruiters.com/v1/companies/ServiceNow/postings?country=ie&limit=100
- https://api.smartrecruiters.com/v1/companies/version1/postings?country=ie&limit=100
- https://api.smartrecruiters.com/v1/companies/statkraft1/postings?country=ie&limit=100
- https://github.com/chinmaykadli/ie-jobs-collector
