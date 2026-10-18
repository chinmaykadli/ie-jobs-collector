"""Public per-job detail fetch for Irish-matched roles whose list feed carries
no description (Workday, SmartRecruiters, Rippling, Workable).

Public GET endpoints only, no accounts. Rate-polite (per-request sleep).
Per-job fetch state lives in state['desc_fetch'][key] so jobs are never
refetched hourly; errors get bounded retries, 404s are permanent.
"""
import json
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


def enrich_missing_descriptions(jobs, state, sleep_s=1.2, max_per_run=250, fetcher=fetch_detail):
    """For Irish-matched jobs with no description, fetch the public detail page.

    Mutates job dicts in place (sets 'description'). Fetch outcomes are
    recorded in state['desc_fetch'][key]: ok / http_404 / error (bounded
    retries). Returns (enriched_count, failed_count, skipped_count).
    """
    dfstate = state.setdefault("desc_fetch", {})
    enriched = failed = skipped = 0
    fetched = 0
    for job in jobs:
        if not job.get("irish_location_match"):
            continue
        if job.get("description"):
            continue
        ats = job.get("ats")
        key = job.get("key")
        url = detail_url(ats, key, job.get("job_url", ""))
        if not url:
            continue
        prior = dfstate.get(key)
        if prior and prior.get("state") == "ok":
            stored = (state.get("jobs", {}).get(key) or {}).get("description")
            if stored:
                # Re-apply the previously fetched description: the list feed never
                # carries one, so skipping without re-applying would flip it back
                # to empty and emit a spurious CHANGED every run.
                job["description"] = stored
                skipped += 1
                continue
            prior = None  # stored description lost (state regression): refetch
        if prior and prior.get("state") == "http_404":
            skipped += 1
            continue
        if prior and prior.get("state") == "error" and prior.get("attempts", 0) >= MAX_RETRIES:
            skipped += 1
            continue
        if fetched >= max_per_run:
            skipped += 1
            continue
        fetched += 1
        try:
            _, payload = fetcher(url)
            desc = extract_description(ats, payload)
            if desc:
                job["description"] = desc
                dfstate[key] = {"state": "ok", "url": url, "attempts": (prior or {}).get("attempts", 0) + 1}
                enriched += 1
            else:
                dfstate[key] = {"state": "error", "url": url, "reason": "empty_description",
                                "attempts": (prior or {}).get("attempts", 0) + 1}
                failed += 1
        except urllib.error.HTTPError as e:
            st = "http_404" if e.code == 404 else "error"
            dfstate[key] = {"state": st, "url": url, "reason": "http_%s" % e.code,
                            "attempts": (prior or {}).get("attempts", 0) + 1}
            failed += 1
        except Exception as e:
            dfstate[key] = {"state": "error", "url": url, "reason": type(e).__name__,
                            "attempts": (prior or {}).get("attempts", 0) + 1}
            failed += 1
        time.sleep(sleep_s)
    return enriched, failed, skipped
