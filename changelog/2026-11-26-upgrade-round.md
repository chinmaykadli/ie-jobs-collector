# Collector upgrades, 26 November 2026

User-approved six-item upgrade round (approved 26 Nov 01:33 UTC: "yes, expand and improve please"). Code only; no source, credential, workflow, qualification-rule or delivery changes.

## 1. Accenture skeletal Workday records

Live probing on 26 Nov (board: accenture.wd103.myworkdayjobs.com, AccentureCareers, "Ireland" search): the records behind the standing quarantine are served by the board with only `bulletFields` (requisition ID and a location label). They carry no `title`, no `externalPath`, no `postedOn` and no `locationsText`, in both the paged list and a targeted single-ID search (verified for R00325027: total 1, same skeletal shape). The cxs detail endpoint 404s without the exact owning path, so titles are not recoverable from the board. The same requisitions are live on the employer's own careers site (accenture.com jobdetails, full JD text indexed); titles verified there for R00325027 (Advertising Sales Rep, Dublin), R00342659 (Process Excellence Senior Manager, Dublin) and R00358960 (GBS Finance Operating Model Consultant, incl. Dublin). That site is a JS shell over a CSRF-protected elastic endpoint; scraping it is brittle and out of this repo's public-ATS-feed design, so no such resolver is added.

Shipped mapping fix: location is recovered from `bulletFields[1]` when `locationsText` is absent (previously dropped), and a skeletal record (no title and no owning path) is classified in quarantine evidence as `record_class: SKELETAL_NO_TITLE_NO_PATH` with `recovered_location`, so the role stays findable by requisition ID and location. Quarantine itself is unchanged: no fabricated title or link, the source stays DEGRADED_PARTIAL, prior jobs and the last full success timestamp are preserved, and a record ingests normally once the board serves full data.

## 2. Pagination proofs for the 39 flagged boards

The 39 pagination-unverified sources are exactly the Ashby (19), Lever (13), Gem (2), Rippling (4) and Workable (1) boards. Their public endpoints return the whole board in a single response with no paging parameters. Live responses checked 26 Nov 01:37 UTC: Ashby `{"jobs", "apiVersion"}`, Lever top-level array, Gem top-level array, Rippling top-level array, Workable widget `{"name", "description", "jobs"}`.

`ats_extra.full_list_pagination` now proves completeness structurally per run: the envelope matches the provider contract, no continuation metadata (`hasMore`, `nextCursor`, `next`, `cursor`, `paging`, etc.) is present, and every row carries a distinct non-empty stable ID. Pass marks the receipt `COMPLETE_EXPLICIT` with a `pagination_proof` (method, envelope, row count, distinct-ID count, API reference). Continuation fields, duplicate or missing IDs fail closed to INCOMPLETE (prior baseline retained); an unexpected envelope stays NOT_VERIFIED. Greenhouse, SmartRecruiters and Workday proofs are unchanged.

## 3. Cache-resistant freshness

A stale cached health response can no longer pass as current: health.json now carries a per-run `run_id` (uuid4), `checked_at`, `expected_interval_seconds` (3600) and `fresh_until` (checked_at + 5400s), plus a `freshness_rule` string spelling out the reader check. A response past `fresh_until` or with a repeating `run_id` is a cached copy. `source_receipt_schema_version` is now 3.

## 4. Raw vs verified-fit counts, review backlog and age

`fit_counts` splits `raw_irish_active`, `remote_country_review_pending`, `verified_fit`, `verified_unfit` and `not_reviewed`. `review_backlog` reports the unreviewed count, the oldest unreviewed `first_seen_at` and its age in days. Review decisions (`review_state`, `reviewed_at`, `review_note`) written into state now persist across runs instead of being reset each run; a materially changed description invalidates the earlier verdict (`review_invalidated_at`/`reason`). Fit itself remains NOT_ASSESSED by the collector; verified counts come from recorded reviews.

## 5. Remote-country eligibility as a review state

Active broad-region remote roles are no longer absent from the queue: they are queued with `eligibility_review_state: REMOTE_COUNTRY_REVIEW_PENDING` (Irish matches keep `IRELAND_LOCATION_MATCHED`). Nothing is excluded for being remote; review resolves country eligibility. raw-irish-queue.json grows accordingly.

## 6. Queue ranking

`ranking.py` orders the queue: review-verified fits, then lane-matched candidates, then remote-review rows, then raw. Inside a tier, roles with an explicit stated closing date rank first (ascending), then the most recently new or changed (`last_changed_at`, now tracked per record). Deadlines come only from an explicit closing/apply-by cue in provider text (common Irish/ISO formats, day-first numerics), validated to a plausible window (yesterday through +150 days); the evidence snippet is kept in `application_deadline_snippet`. No cue or an implausible date leaves the role undated, never excluded.

## Tests and rollback

25 new tests (pagination proofs, freshness, review persistence and invalidation, backlog age, remote queuing, deadline parsing, rank order, skeletal records); one existing quarantine test updated for the enriched skeletal evidence. Full suite: 71 tests plus 13 description tests pass. Changed files: ingest.py, ats_extra.py, ranking.py (new), README.md, tests/. Rollback: revert this commit only, preserving hourly data commits; re-run both test commands; verify the next ordinary collector health receipt before calling it live.

## Public sources

- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://github.com/lever/postings-api/
- https://api.ashbyhq.com/posting-api/job-board/wayflyer?includeCompensation=true
- https://api.lever.co/v0/postings/analyticpartners?mode=json
- https://api.gem.com/job_board/v0/biorender/job_posts/
- https://api.rippling.com/platform/api/ats/v1/board/allied-global-marketing/jobs
- https://apply.workable.com/api/v1/widget/accounts/crown-global
- https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs
- https://www.accenture.com/ie-en/careers/jobdetails?id=R00325027_en
