# Weekly collector review - 1 November 2026

## Verified result
A sandbox-tested fix removes false changes when a multi-location feed returns the same locations in a different order. One live Rippling payload was replayed in forward and reverse order. Baseline: 138 false changes. Proposed: zero. Both versions retained exactly 373 job IDs and 37 Irish jobs. Seven regression tests pass, including genuine location additions/removals, title changes and foreign-Dublin protection.

## Yield assessment
Latest public snapshot: 31 October 23:41 UTC, 135 configured boards, 2,108 active Irish raw listings, no degraded sources in that snapshot. This does not establish hourly reliability or qualified-role yield. Scheduled delivery remains unreliable and its separate recovery gate remains unmet.

The stored journal is capped at 5,000 events and covers only 29 October 20:33 through 31 October 23:41, not the full week. Within that bounded sample: 381 new raw records, 67 Irish; 4,155 change events; 2,971 timestamp-only changes; 503 location-only changes, of which 491 were Rippling. These are collection events, not approved opportunities or unique weekly outcomes. Qualified yield cannot be measured from this store because qualification_state remains NOT_ASSESSED.

Irish NEW events by provider in this sample: {'greenhouse': 14, 'workday': 30, 'smartrecruiters': 13, 'ashby': 6, 'workable': 1, 'lever': 2, 'rippling': 1}. No source was removed based on this incomplete sample.

## Endpoint investigation
The existing public Rippling board endpoint remains readable without accounts. Duplicate location rows for a stable job ID can arrive in a different order, causing joined location strings to change. The proposed parser sorts and deduplicates locations and compares location sets only for Rippling/Workable. It does not suppress real location changes, change Ireland eligibility rules, change source coverage, touch accounts or change the dashboard.

## Change and rollback
Not deployed. The attached patch changes ingest.py and ats_extra.py and adds tests/test_multilocation.py. No state files, public data, workflows, sources or credentials were changed. Apply to base commit 0edccb4 after checking the current branch. Run python -m unittest discover -s tests -v. Roll back with git apply -R multilocation.patch if no later dependent changes exist, or revert the dedicated code commit. Keep feed/data pushes paused under the existing recovery rule.

## Sources
- Public repository: https://github.com/chinmaykadli/ie-jobs-collector
- Live endpoint: https://api.rippling.com/platform/api/ats/v1/board/rippling/jobs
- Snapshot source files: sources.json, docs-data/health.json, state/state.json.gz at base commit 0edccb4.
