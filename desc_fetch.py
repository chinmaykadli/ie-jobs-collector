"""Public per-job detail fetch for Irish-matched roles whose list feed carries
no description (Workday, SmartRecruiters, Rippling, Workable).

Public GET endpoints only, no accounts. Rate-polite (per-request sleep).
Per-job cache expires and is invalidated by source changes. Failed refreshes
retain old text with an explicit stale label; no result implies eligibility.
"""
import json
import hashlib
from datetime import datetime, timezone
import time
import urllib.error
import urllib.request

UA = {"Accept": "application/json", "User-Agent": "PersonalJobFeedResearch/0.1"}
MAX_RETRIES = 3


def detail_url(ats, key, job_url):
    """Build the public detail URL for a queue record, or None if unsupported."""
    parts = key.split(":", 2)
    if len(parts) != 3:
        return None
    _, company, jid = parts
    if ats == "smartrecruiters":
        return "https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (company, jid)
    if ats == "workday":
        if not job_url:
            return None
        segs = job_url.split("/")
        host = segs[2]
        rest = "/".join(segs[4:])
        site = segs[3]
        return "https://%s/wday/cxs/%s/%s/%s" % (host, company, site, rest)
    if ats == "rippling":
        return "https://api.rippling.com/platform/api/ats/v1/board/%s/jobs/%s" % (company, jid)
    if ats == "workable":
        return "https://apply.workable.com/api/v1/accounts/%s/jobs/%s" % (company, jid)
    return None


def extract_description(ats, payload):
    """Pull the description HTML out of a decoded detail payload."""
    if ats == "workday":
        return payload.get("jobPostingInfo", {}).get("jobDescription") or ""
    if ats == "smartrecruiters":
        sections = payload.get("jobAd", {}).get("sections", {})
        if isinstance(sections, dict):
            texts = [v.get("text", "") for v in sections.values() if isinstance(v, dict)]
        else:
            texts = [v.get("text", "") for v in sections if isinstance(v, dict)]
        return "".join(texts)
    if ats == "rippling":
        d = payload.get("description", {})
        return (d.get("company", "") or "") + (d.get("role", "") or "")
    if ats == "workable":
        out = payload.get("description", "") or ""
        for label, fld in (("Requirements", "requirements"), ("Benefits", "benefits")):
            extra = payload.get(fld)
            if extra:
                out += "<h3>%s</h3>%s" % (label, extra)
        return out
    return ""


def fetch_detail(url, timeout=15):
    """GET a detail URL. Returns (status, payload_dict) or raises urllib errors."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), json.load(resp)


CACHE_SCHEMA = 2
SUCCESS_TTL = 24 * 3600
ERROR_TTL = 6 * 3600
NOT_FOUND_TTL = 24 * 3600


def source_signature(job):
    fields = [job.get(k) for k in ("job_url", "title", "source_updated_at")]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def enrich_missing_descriptions(jobs, state, sleep_s=1.2, max_per_run=250,
                                fetcher=fetch_detail, now_fn=time.time, deadline=None):
    """Refresh empty-list descriptions using a bounded, expiring cache.

    Old caches have no freshness proof and must be fetched again. Source URL,
    title or update changes invalidate cached success and failure alike.
    """
    dfstate = state.setdefault("desc_fetch", {})
    enriched = failed = skipped = fetched = 0
    for job in jobs:
        if not job.get("irish_location_match") or job.get("description"):
            continue
        ats, key = job.get("ats"), job.get("key")
        url = detail_url(ats, key, job.get("job_url", ""))
        if not url:
            continue
        now = now_fn()
        signature = source_signature(job)
        prior = dfstate.get(key) or {}
        stored = (state.get("jobs", {}).get(key) or {}).get("description")
        valid = (prior.get("schema") == CACHE_SCHEMA and prior.get("url") == url
                 and prior.get("source_signature") == signature)
        checked = prior.get("checked_at_epoch", 0)
        ttl = SUCCESS_TTL if prior.get("state") == "ok" else (NOT_FOUND_TTL if prior.get("state") == "http_404" else ERROR_TTL)
        fresh = valid and 0 <= now - checked < ttl
        if stored:
            job["description"] = stored
            job["description_state"] = "PRESENT"
            job["description_freshness"] = "FRESH_CACHE" if fresh and prior.get("state") == "ok" else "STALE_CACHE"
            job["description_checked_at"] = prior.get("checked_at")
        if fresh and (prior.get("state") != "ok" or stored):
            skipped += 1
            continue
        if fetched >= max_per_run or (deadline is not None and time.monotonic() >= deadline):
            job.setdefault("description_state", "MISSING")
            job.setdefault("description_freshness", "NOT_FETCHED")
            skipped += 1
            continue
        fetched += 1
        outcome = {"schema": CACHE_SCHEMA, "url": url, "source_signature": signature,
                   "checked_at_epoch": now, "checked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                   "attempts": prior.get("attempts", 0) + 1}
        try:
            _, payload = fetcher(url)
            desc = extract_description(ats, payload)
            if desc.strip():
                job.update(description=desc, description_state="PRESENT", description_freshness="FRESH_DETAIL",
                           description_checked_at=outcome["checked_at"])
                outcome["state"] = "ok"
                enriched += 1
            else:
                outcome.update(state="error", reason="empty_description")
                failed += 1
        except urllib.error.HTTPError as e:
            outcome.update(state="http_404" if e.code == 404 else "error", reason="http_%s" % e.code)
            failed += 1
        except Exception as e:
            outcome.update(state="error", reason=type(e).__name__)
            failed += 1
        dfstate[key] = outcome
        if outcome["state"] != "ok":
            job.setdefault("description_state", "MISSING")
            job["description_freshness"] = "STALE_CACHE" if stored else "FETCH_FAILED"
        time.sleep(sleep_s)
    return enriched, failed, skipped
