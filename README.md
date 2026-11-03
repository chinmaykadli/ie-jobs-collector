# ie-jobs-collector
Public-job-board collector for Ireland-based roles. Hourly GitHub Actions run pulls public ATS feeds (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Recruitee, Gem, Rippling) and commits the raw public listings under docs-data/. Public job data only - no personal data, no credentials.

Description handling: full provider text is retained, with no 4,000-character truncation. Detail-only descriptions have a 24-hour successful-cache TTL; title, URL or provider-updated changes invalidate the cache. Failed refreshes retain old text explicitly marked STALE_CACHE. Failed requests wait six hours, and 404s wait 24 hours before another attempt. Legacy caches without freshness metadata are refreshed gradually. Each run allows at most 100 detail requests and six minutes of detail-refresh start time, so a migration cannot create an unbounded request burst. Deferred descriptions remain explicitly missing or stale; these are not eligibility clearances.

Regression tests: `python -m unittest discover -s tests -v` and `python -m unittest test_descriptions -v`.

Workday malformed-record quarantine: records with a stable ID but missing title or owning path are quarantined with ID and reason. Valid records remain ingestible, while the source is explicitly DEGRADED_PARTIAL. A partial source never advances its last fully successful timestamp or marks unseen prior jobs removed. Missing stable identity or unknown schema errors still fail closed. Quarantine evidence is in source health and durable source state; it does not qualify vacancies or enable delivery.
