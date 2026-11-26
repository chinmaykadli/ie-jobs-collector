"""Queue ordering for the raw Irish queue: review-backed or lane-matched roles
first, real stated deadlines before undated roles, then most recently
new/changed. Ranking orders review; it is not a fit or eligibility verdict.

Deadlines are extracted only from an explicit closing/apply-by cue in the
provider text, kept as evidence with the matched snippet. No cue, no date, an
implausible or past date means the role stays undated; an undated role is never
penalised out of the queue, only ordered after dated ones within its tier."""
import re
from datetime import datetime, timedelta, timezone

CUE = re.compile(
    r'(?:closing date|apply by|application deadline|applications? close[sd]?|'
    r'closing on|deadline for applications|closing for applications)'
    r'(?:\s*(?:is|on|:|-))?', re.I)

MONTHS = {m: i for i, m in enumerate(
    ('january february march april may june july august september october '
     'november december').split(), 1)}
MONTH_RE = '|'.join(list(MONTHS) + [m[:3] for m in MONTHS])

PATTERNS = (
    # 15 December 2026 / 15th Dec 2026 / 15 Dec 26
    re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s)\.?,?\s+(\d{2,4})\b' % MONTH_RE, re.I),
    # December 15, 2026 / Dec 15 26
    re.compile(r'\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{2,4})\b' % MONTH_RE, re.I),
    # 2026-12-15
    re.compile(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b'),
    # 15/12/2026 or 15-12-26 (day first, Irish convention)
    re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b'),
)

WINDOW = 150  # days ahead a stated deadline is still plausible


def _month_num(name):
    return MONTHS.get(name.lower()) or MONTHS.get(name.lower()[:3])


def _valid(day, month, year, today):
    if year < 100:
        year += 2000
    try:
        d = datetime(year, month, day, tzinfo=timezone.utc).date()
    except ValueError:
        return None
    if d < today - timedelta(days=1) or d > today + timedelta(days=WINDOW):
        return None
    return d


def parse_deadline(text, today=None):
    """First explicit application-deadline date in provider text, or None.

    Returns (iso_date, snippet) so the queue keeps the evidence next to the
    value. Only dates near a closing/apply-by cue count."""
    if not text:
        return None, None
    today = today or datetime.now(timezone.utc).date()
    for cue in CUE.finditer(text):
        window = text[cue.start():cue.end() + 80]
        for pat in PATTERNS:
            m = pat.search(window)
            if not m:
                continue
            g = m.groups()
            if pat is PATTERNS[0]:
                d = _valid(int(g[0]), _month_num(g[1]) or 0, int(g[2]), today)
            elif pat is PATTERNS[1]:
                d = _valid(int(g[1]), _month_num(g[0]) or 0, int(g[2]), today)
            elif pat is PATTERNS[2]:
                d = _valid(int(g[2]), int(g[1]), int(g[0]), today)
            else:
                d = _valid(int(g[0]), int(g[1]), int(g[2]), today)
            if d:
                return d.isoformat(), ' '.join(window.split())[:120]
    return None, None


TIER_ORDER = {'VERIFIED_FIT': 0, 'CONTEXT_MATCH': 1, 'REMOTE_COUNTRY_REVIEW': 2, 'RAW': 3}


def rank_tier(job):
    if job.get('review_state') == 'VERIFIED_FIT':
        return 'VERIFIED_FIT'
    if not job.get('irish_location_match') and job.get('remote_ireland_eligibility_unverified'):
        return 'REMOTE_COUNTRY_REVIEW'
    if job.get('context_candidate'):
        return 'CONTEXT_MATCH'
    return 'RAW'


def rank_queue(queue, today=None):
    """Annotate each queued job with deadline evidence, tier and 1-based rank,
    and return the queue in rank order. Input records are copied, not mutated."""
    today = today or datetime.now(timezone.utc).date()
    rows = []
    for job in queue:
        j = dict(job)
        iso, snippet = parse_deadline(j.get('description', ''), today)
        j['application_deadline'] = iso
        if snippet:
            j['application_deadline_snippet'] = snippet
        j['rank_tier'] = rank_tier(j)
        changed = j.get('last_changed_at') or j.get('first_seen_at') or ''
        rows.append((TIER_ORDER[j['rank_tier']], 0 if iso else 1, iso or '',
                     -_epoch(changed), j['company'], j['title'], j))
    # tier first; deadline ascending inside tier; then newest change first
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3], r[4], r[5]))
    out = []
    for i, r in enumerate(rows, 1):
        r[6]['queue_rank'] = i
        out.append(r[6])
    return out


def _epoch(iso):
    try:
        return datetime.fromisoformat(str(iso).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0.0
