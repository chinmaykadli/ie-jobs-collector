# Weekly collector review, 22 November 2026

## Verified improvement
A single Ashby posting with a stable ID but a blank or absent title no longer blocks every valid posting from that source. The malformed record is quarantined with its ID and reason. Missing identity, malformed record objects, unexpected title types, missing owning URLs and other providers still fail closed. No network request or new endpoint is added.

The existing partial-source reconciliation path remains in charge: valid posts refresh, unseen prior posts remain active but stale, no feed removals are emitted, the last fully successful timestamp is retained, and source health is DEGRADED_PARTIAL with a quarantine count. All-quarantined responses are not healthy zeroes. A genuine empty array still follows the ordinary zero-result path. Feed disappearance is not an employer-closure claim. Qualification remains NOT_ASSESSED and standing delivery remains off.

On 22 Nov 04:49 UTC, the public OpenAI response returned 852 records, one with a blank title. The published source health had 30 consecutive failures and last full success 16 Nov 16:38 UTC. The patch reads 851 valid records and quarantines that one ID. Eighteen valid records have an Irish location. Two IDs are absent from the current Irish queue: Privacy Operations Analyst and Technical Operations Analyst, Automation & Evaluations. This is a queue comparison, not proof that the roles are new to the user's history, qualified, or applications to make.

Wayflyer 13 and Notion 170 live records are unchanged as normalized JSON. All 851 valid OpenAI records are also identical to baseline normalization after removing only the malformed fixture. Nine new regression tests plus the existing 50 tests pass, 59 total. Tests cover partial refresh, preserved prior jobs and last full success, no false removals, new valid records, all-quarantined vs genuine empty, healthy records, and fail-closed cases.

An offline replay against the actual prior OpenAI state refreshed 18 current Irish records, retained one unseen prior Irish record as stale, discovered the two Irish IDs above, and emitted zero removals. The last fully successful timestamp did not advance. HTTP receipt verification in this replay is intentionally false because it used the captured response, not a new network request.

## Bounded source yield
Current published snapshot: 22 Nov 00:39 UTC, 135 configured boards, 2,036 active Irish raw records. Thirty-six retained Irish snapshots cover the 17 Nov 00 run through the 22 Nov 00 run, not the whole 15-22 Nov week. Across those snapshots 240 distinct keys appear between adjacent available snapshots: Workday 105, SmartRecruiters 64, Greenhouse 50, Ashby 15, Rippling 4 and Lever 2.269 distinct keys disappear at least once. Reappearances and gaps are included; these are not 240 new roles, 269 closed jobs or qualified/application yield.

The 5,000-event retained journal covers 19 Nov 22:25 UTC through 22 Nov 00:39 UTC. It contains 537 NEW raw events, 3,850 CHANGED, 583 REMOVED_FROM_FEED and 30 REAPPEARED. Of these, 72 NEW have current stored Irish-location evidence: Workday 29, Greenhouse 18, SmartRecruiters 18, Ashby 6, Rippling 1.3,253 of 3,850 CHANGED events change only source_updated_at. Source health has 132 OK_NONEMPTY, 2 OK_ZERO and 1 ERROR, 39 pagination-unverified boards. Qualification is NOT_ASSESSED, so opportunity-to-application yield cannot be calculated from this store. No source is removed based on this incomplete sample.

## Endpoint investigation
Ashby's current official public API documentation includes all published jobs, primary/secondary locations and optional compensation. Existing code already reads secondary location labels, so that is not presented as a new improvement. Structured country fields deserve a separate location-evidence test, not an untested policy change. One read each of AbbVie 67, Eurofins 42 and SGS 19 Ireland-filtered SmartRecruiters records found no demonstrated Irish-location miss in that sample. Existing SmartRecruiters completeness checks remain unchanged. No direct Workday requests, new paid tool, new source, authenticated feed or careers watcher is added.

## Scope, publication and rollback
Changed files: ingest.py, tests/test_ashby_quarantine.py and this changelog. No credentials, account settings, source configuration, workflow, user location/pay/experience/permission rules, dashboard, generated state or delivery setting changes.

The dedicated code commit containing this changelog is the rollback unit. Revert only that commit, preserving subsequent hourly data commits. Re-run python -m unittest discover -s tests -v and python -m unittest test_descriptions -v. Do not restore an old generated state snapshot or treat retained stale roles as current. The current hourly guard and workflow are unchanged. Verify the resulting remote code and a subsequent ordinary collector health receipt before calling the fix live. Local tests alone do not prove deployment.

## Public sources
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://api.ashbyhq.com/posting-api/job-board/openai?includeCompensation=true
- https://api.ashbyhq.com/posting-api/job-board/wayflyer?includeCompensation=true
- https://api.ashbyhq.com/posting-api/job-board/notion?includeCompensation=true
- https://api.smartrecruiters.com/v1/companies/abbvie/postings?country=ie&limit=100
- https://api.smartrecruiters.com/v1/companies/eurofins/postings?country=ie&limit=100
- https://api.smartrecruiters.com/v1/companies/sgs/postings?country=ie&limit=100
- https://github.com/chinmaykadli/ie-jobs-collector
