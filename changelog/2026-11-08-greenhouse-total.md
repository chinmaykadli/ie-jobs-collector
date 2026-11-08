# Weekly collector review - 8 November 2026

## Verified improvement
Greenhouse list responses now check their documented `meta.total` against both row count and distinct stable IDs. A matching, well-formed count provides explicit completeness evidence for that response. Missing metadata remains NOT_VERIFIED. Conflicting continuation signals, count mismatches, duplicate IDs or malformed advertised totals fail closed, retain prior jobs as stale, and do not emit removals or advance last success. This does not establish current vacancy closure or qualification.

Three public boards were read once each: Intercom (109 posts, 41 Irish), Tines (34, 8), Stripe (766, 93). All 909 posts and 142 Irish location matches are retained unchanged; completeness evidence changes from NOT_VERIFIED to COMPLETE_EXPLICIT. This is a three-board sample, not verification of all 56 configured Greenhouse boards.

A synthetic truncated response with one row and total two demonstrates the safety difference: baseline emits one false removal and retains one active Irish job; the fix emits zero removals and retains both prior jobs as stale. Valid subsequent one-row/total-one responses and explicit zero responses still reconcile normally. Six new regression tests plus the existing 33 tests pass (39 total).

## Source yield
Snapshot: 8 November 04:38 UTC, 135 configured boards, 2,089 active Irish raw records. The retained journal is exactly 5,000 events from 5 November 19:38 through 8 November 04:38, not a full week. It contains 495 NEW raw events, 62 Irish, 3,955 CHANGED, 539 REMOVED_FROM_FEED and 11 REAPPEARED. Irish NEW by provider: Workday 25, Greenhouse 16, SmartRecruiters 10, Ashby 8, Lever 3. Of the CHANGED events, 1,470 are source_updated_at-only; 1,121 description-only; 543 job_url/apply_url-only. No source is removed based on this incomplete sample. Raw events are not qualified opportunities: qualification_state remains NOT_ASSESSED. Timestamp and URL changes are retained, not silently suppressed.

## Investigation and scope
Greenhouse's public Job Board API documents the jobs/meta.total envelope and unauthenticated GET. The Ashby public API documents all published jobs but no per-response total counter, so it remains unchanged and NOT_VERIFIED here. Workday's known malformed record remains quarantined; this change does not guess its missing title/path or lift partial coverage. No new boards, location/pay/eligibility rules, accounts, spending, dashboard, workflow, careers watcher or delivery settings change. Standing feed stays off.

## Deployment and rollback
Only ingest.py, ats_extra.py, tests/test_greenhouse_total.py and this changelog change. A dedicated code commit can be reverted with `git revert <the commit containing this changelog>`, retaining later data commits and source configuration. Re-run `python -m unittest discover -s tests -v` and `python -m unittest test_descriptions -v`. Generated snapshots/state are not part of the code change. The existing workflow may run on push, but its UTC-hour guard skips an already published hour.

## Sources
- https://docs.greenhouse.io/job-board.html
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://boards-api.greenhouse.io/v1/boards/intercom/jobs?content=true
- https://boards-api.greenhouse.io/v1/boards/tines/jobs?content=true
- https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true
- https://github.com/chinmaykadli/ie-jobs-collector
