"""Drop-in extension for ingest.py: smartrecruiters, workable, recruitee (plain GET) and workday (POST fetcher).
Does not replace ingest.py. `import ats_extra` patches ingest.normalize and ingest.pagination_evidence;
greenhouse/ashby/lever behaviour is untouched (original functions are called for them)."""
import json, urllib.request, urllib.error, re, time
import ingest as I
_orig_norm, _orig_page = I.normalize, I.pagination_evidence
EXTRA = {'smartrecruiters', 'workable', 'recruitee', 'workday', 'gem', 'rippling'}
TAG = re.compile(r'<[^>]+>')

import io, types

class _Resp(io.BytesIO):
    def __init__(self, data, code=200): super().__init__(data); self._c = code
    def getcode(self): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False

def workday_pull(url, search='Ireland', max_pages=15):
    """Paged POST to a Workday cxs endpoint. Any failed page raises (HTTPError keeps its status for ingest backoff).
    complete=True only when the provider total is known and fully read, or a short final page proves the end.
    A full page at max_pages with no total is INCOMPLETE. Scope is the Ireland search only, not the whole board."""
    out, total, offset, last_len, statuses = [], None, 0, 0, []
    for _ in range(max_pages):
        body = json.dumps({'appliedFacets': {}, 'limit': 20, 'offset': offset, 'searchText': search}).encode()
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'PersonalJobFeedResearch/0.1'})
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.getcode()
            d = json.load(r)
        if not isinstance(code, int) or not 200 <= code < 300: raise ValueError('Workday page %d unexpected HTTP status %r' % (len(statuses) + 1, code))
        statuses.append(code)
        page = d.get('jobPostings')
        if not isinstance(page, list): raise ValueError('Workday schema drift: jobPostings missing')
        if offset == 0 and isinstance(d.get('total'), int): total = d['total']
        out += page; offset += 20; last_len = len(page)
        if last_len < 20: break
        if total is not None and offset >= total: break
    if total is not None: complete = len(out) >= total
    else: complete = last_len < 20
    return {'jobs': out, 'total': total, 'complete': complete, 'scope': 'BOUNDED_SEARCH:' + search, 'page_statuses': statuses}

def _urlopen(req, timeout=None):
    """Used only inside ingest: Workday cxs URLs get the paged POST but still run through ingest's own
    HTTP receipt, error and Retry-After backoff path; everything else is the normal GET."""
    url = req.full_url if hasattr(req, 'full_url') else req
    if '/wday/cxs/' in url:
        base, _, q = url.partition('?')
        search = (urllib.parse.parse_qs(q).get('q') or ['Ireland'])[0]
        res = workday_pull(base, search)
        # aggregate status = observed status of the last real page; every page was checked 2xx and is listed in page_statuses
        return _Resp(json.dumps(res).encode(), res['page_statuses'][-1])
    return urllib.request.urlopen(req, timeout=timeout)
import urllib.parse
I.urllib = types.SimpleNamespace(request=types.SimpleNamespace(Request=urllib.request.Request, urlopen=_urlopen), error=urllib.error)

def smartrecruiters_pagination_evidence(payload):
    """A list page is complete only from offset zero, with every distinct ID.
    ListResult documents totalFound before limit/offset. Never treat duplicated
    rows, a later page, or contradictory continuation metadata as a full feed.
    No extra requests are made; incomplete responses retain the prior baseline.
    """
    if not isinstance(payload, dict): return 'NOT_VERIFIED'
    if payload.get('hasMore') is True or payload.get('has_more') is True:
        return 'INCOMPLETE'
    if any(payload.get(k) for k in ('nextPage', 'next_page', 'nextCursor')):
        return 'INCOMPLETE'
    if 'totalFound' not in payload: return 'NOT_VERIFIED'
    def count(value):
        if type(value) is int and value >= 0: return value
        # ListResult lists string types; live responses also use JSON integers.
        if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
            return int(value)
        return None
    total, offset = count(payload['totalFound']), count(payload.get('offset'))
    rows = payload.get('content')
    if total is None or offset != 0 or not isinstance(rows, list):
        return 'INCOMPLETE'
    ids = [row.get('id') if isinstance(row, dict) else None for row in rows]
    valid = all(type(jid) in (int, str) and str(jid).strip() for jid in ids)
    complete = valid and total == len(rows) == len({str(jid) for jid in ids})
    return 'COMPLETE_EXPLICIT' if complete else 'INCOMPLETE'


CONTINUATION_KEYS = ('hasMore', 'has_more', 'nextPage', 'next_page', 'nextCursor',
                     'next', 'cursor', 'nextUrl', 'next_page_url', 'paging',
                     'continuationToken', 'continuation')

# Providers whose public board endpoint returns the whole board in one response,
# documented as a full list with no paging parameters. The proof is structural:
# the envelope matches that contract, no continuation metadata is present, and
# every row carries a distinct stable ID. Duplicated rows or continuation fields
# fail closed to INCOMPLETE; an unexpected envelope stays NOT_VERIFIED.
FULL_LIST_CONTRACTS = {
    'ashby': {'envelope': 'dict:jobs+apiVersion', 'ids': lambda j: j.get('id'),
              'docs': 'https://developers.ashbyhq.com/docs/public-job-posting-api'},
    'lever': {'envelope': 'top-level array', 'ids': lambda j: j.get('id'),
              'docs': 'https://github.com/lever/postings-api/'},
    'gem': {'envelope': 'top-level array', 'ids': lambda j: j.get('id') or j.get('internal_job_id'),
            'docs': 'https://api.gem.com/job_board/v0/'},
    'rippling': {'envelope': 'top-level array', 'ids': lambda j: j.get('uuid'),
                 'docs': 'https://api.rippling.com/platform/api/ats/v1/'},
    'workable': {'envelope': 'dict:jobs+name', 'ids': lambda j: j.get('shortcode') or j.get('id'),
                 'docs': 'https://apply.workable.com/api/v1/widget/accounts/'},
}


def full_list_pagination(payload, source):
    """Returns (state, proof|None) for single-response full-list providers."""
    if not source:
        return None, None
    contract = FULL_LIST_CONTRACTS.get(source.get('ats'))
    if contract is None:
        return None, None
    if contract['envelope'].startswith('dict'):
        if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
            return 'NOT_VERIFIED', None
        rows = payload['jobs']
        if source.get('ats') == 'ashby' and not payload.get('apiVersion'):
            return 'NOT_VERIFIED', None
        if source.get('ats') == 'workable' and not isinstance(payload.get('name'), str):
            return 'NOT_VERIFIED', None
        continuation = [k for k in CONTINUATION_KEYS if payload.get(k)]
    else:
        if not isinstance(payload, list):
            return 'NOT_VERIFIED', None
        rows = payload
        continuation = []
    if continuation:
        return 'INCOMPLETE', None
    ids = [contract['ids'](j) if isinstance(j, dict) else None for j in rows]
    valid = all(type(jid) in (int, str) and str(jid).strip() for jid in ids)
    distinct = len({str(jid) for jid in ids})
    if not valid or distinct != len(rows):
        return 'INCOMPLETE', None
    proof = {'method': 'PROVIDER_FULL_LIST_CONTRACT',
             'envelope': contract['envelope'],
             'rows': len(rows),
             'distinct_stable_ids': distinct,
             'continuation_fields_present': False,
             'api_reference': contract['docs']}
    return 'COMPLETE_EXPLICIT', proof


def pagination_proof(payload, source, state):
    """Receipt detail for a COMPLETE_EXPLICIT verdict from the full-list path."""
    if state != 'COMPLETE_EXPLICIT':
        return None
    _state, proof = full_list_pagination(payload, source)
    return proof


def pagination_evidence(payload, source=None):
    if source and source.get('ats') in FULL_LIST_CONTRACTS:
        state, _proof = full_list_pagination(payload, source)
        if state is not None:
            return state
    if source and source.get('ats') == 'smartrecruiters':
        return smartrecruiters_pagination_evidence(payload)
    if source and source.get('ats') == 'greenhouse':
        return _orig_page(payload, source)
    if isinstance(payload, dict):
        if 'complete' in payload: return 'COMPLETE_EXPLICIT' if payload['complete'] else 'INCOMPLETE'
        if 'totalFound' in payload and isinstance(payload.get('content'), list):
            return 'COMPLETE_EXPLICIT' if payload['totalFound'] <= len(payload['content']) else 'INCOMPLETE'
    return _orig_page(payload, source)

class NormalizedJobs(list):
    """Valid records plus explicit provider-record quarantine evidence."""
    pass

def normalize(source, payload):
    ats = source['ats']
    if ats not in EXTRA: return _orig_norm(source, payload)
    key = {'smartrecruiters': 'content', 'workable': 'jobs', 'recruitee': 'offers', 'workday': 'jobs', 'gem': None, 'rippling': None}[ats]
    if key is None:  # gem/rippling return a top-level JSON array
        if not isinstance(payload, list): raise ValueError('Expected %s top-level array, schema drift not zero' % ats)
        items = payload
    else:
        if not isinstance(payload, dict) or not isinstance(payload.get(key), list): raise ValueError('Expected %s array, schema drift not zero' % key)
        items = payload[key]
    res = []
    quarantine = []
    for j in items:
        if not isinstance(j, dict): raise ValueError('Job item not an object')
        if ats == 'smartrecruiters':
            jid, title, url = j.get('id'), j.get('name'), None
            l = j.get('location') or {}
            loc = ', '.join(x for x in [l.get('city'), l.get('region'), (l.get('country') or '').upper()] if x)
            if jid: url = 'https://jobs.smartrecruiters.com/%s/%s' % (source['token'], jid)
            posted, dtype, desc, upd = j.get('releasedDate'), 'releasedDate', '', None
            if not l.get('country'): loc = (loc + ' (country not stated)').strip()
        elif ats == 'workable':
            jid, title, url = j.get('shortcode') or j.get('id'), j.get('title'), j.get('url')
            loc = ', '.join(x for x in [j.get('city'), j.get('state'), j.get('country')] if x)
            posted, dtype, desc, upd = j.get('published_on'), 'published_on_date', TAG.sub(' ', j.get('description') or ''), None
        elif ats == 'recruitee':
            jid, title, url = j.get('id'), j.get('title'), j.get('careers_url')
            loc = j.get('location') or ', '.join(x for x in [j.get('city'), j.get('country')] if x)
            posted, dtype, desc, upd = j.get('published_at'), 'published_at', TAG.sub(' ', (j.get('description') or '') + ' ' + (j.get('requirements') or '')), None
        elif ats == 'gem':
            jid, title, url = j.get('id') or j.get('internal_job_id'), j.get('title'), j.get('absolute_url')
            loc = (j.get('location') or {}).get('name', '') if isinstance(j.get('location'), dict) else (j.get('location') or '')
            posted, dtype, desc, upd = j.get('first_published_at'), 'first_published_at', j.get('content_plain') or TAG.sub(' ', j.get('content') or ''), j.get('updated_at')
        elif ats == 'rippling':
            jid, title, url = j.get('uuid'), (j.get('name') or '').strip(), j.get('url')
            loc = (j.get('workLocation') or {}).get('label', '')
            posted, dtype, desc, upd = None, 'not_provided', '', None
        else:
            bf = j.get('bulletFields') or []
            jid = (bf + [None])[0] or j.get('externalPath'); title = j.get('title')
            base = source['url'].split('/wday/')[0]; site = source['url'].split('/cxs/')[1].split('/')[1]
            url = base + '/' + site + j['externalPath'] if j.get('externalPath') else None
            # Skeletal Workday rows (no locationsText) still carry the location
            # label as bulletFields[1]; recover it instead of dropping it.
            loc = j.get('locationsText') or (str(bf[1]) if len(bf) > 1 and bf[1] else '')
            posted, dtype, desc, upd = j.get('postedOn'), 'relative_text_not_a_date', '', None
        if jid is None: raise ValueError('Job missing stable id')
        if ats == 'workday' and (not title or not j.get('externalPath')):
            rec = {'id': str(jid), 'reason': 'Job missing title' if not title else 'Missing authoritative job link'}
            if not title and not j.get('externalPath'):
                # Skeletal record: the board serves only a stable ID and a
                # location label. Title and owning path are not recoverable
                # from the feed; keep the evidence so the role stays findable.
                rec['record_class'] = 'SKELETAL_NO_TITLE_NO_PATH'
                if loc: rec['recovered_location'] = loc
            quarantine.append(rec)
            continue
        if not title: raise ValueError('Job missing title')
        if not url or not url.startswith('https://'): raise ValueError('Missing authoritative job link')
        ireland = I.irish_location(loc) and not (ats == 'smartrecruiters' and not (j.get('location') or {}).get('country')) and not re.search(r'\bnot stated\b', loc)
        nodesc = ats in ('smartrecruiters', 'workday', 'rippling') or not desc.strip()
        res.append({'key': '%s:%s:%s' % (ats, source['token'], jid), 'company': source['company'], 'ats': ats, 'id': str(jid), 'title': title, 'location': loc,
                    'irish_location_match': ireland, 'remote_ireland_eligibility_unverified': bool(I.remote_ireland_pending(loc, ireland)),
                    'context_candidate': bool(I.LANES.search(title + ' ' + desc)) and not nodesc, 'description_state': 'MISSING' if nodesc else 'PRESENT', 'coverage_scope': ('BOUNDED_SEARCH_IRELAND_NOT_GLOBAL' if ats == 'workday' else 'FULL_FEED_PAGINATION_PER_RECEIPT'), 'job_url': url, 'apply_url': None,
                    'source_posted_at': posted, 'source_posted_at_utc': I.posted_utc(posted, dtype) if dtype in ('releasedDate', 'published_at', 'first_published_at') else None,
                    'source_posted_at_original': posted, 'source_updated_at': upd, 'timestamp_semantics': dtype, 'employment_type': None,
                    'description': desc, 'review_state': 'NOT_REVIEWED', 'source_url': source['url']})
    result = NormalizedJobs(_merge_dupes(res))
    result.quarantined_records = quarantine
    return result

def _merge_dupes(res):
    """Rippling/Workable list one row per (job, location) under the same id. Merge them into one record per key,
    locations joined with '; ', Irish match if any location is Irish. Stops last-row-wins location flip-flop (CHANGED churn)."""
    out, idx = [], {}
    for r in res:
        k = r['key']
        if k not in idx: idx[k] = len(out); out.append(r); continue
        m = out[idx[k]]
        locs = [x.strip() for x in m['location'].split(';') if x.strip()]
        if r['location'] and r['location'].strip() not in locs: locs.append(r['location'].strip())
        m['location'] = '; '.join(locs)
        m['irish_location_match'] = bool(m['irish_location_match'] or r['irish_location_match'])
        m['remote_ireland_eligibility_unverified'] = bool(m['remote_ireland_eligibility_unverified'] or r['remote_ireland_eligibility_unverified'])
        m['context_candidate'] = bool(m['context_candidate'] or r['context_candidate'])
    # Provider order is not a meaningful location change. Keep all locations.
    for record in out:
        record['location'] = '; '.join(sorted({x.strip() for x in record['location'].split(';') if x.strip()}))
    return out

I.normalize, I.pagination_evidence = normalize, pagination_evidence
I.pagination_proof_fn = pagination_proof

def run(sources, out):
    """All sources, including Workday, go through ingest's own fetch, receipts and backoff path."""
    global _detail_remaining, _detail_deadline
    _detail_remaining, _detail_deadline = 100, time.monotonic() + 360
    return I.ingest(sources, out)


_detail_remaining, _detail_deadline = 100, None

def _desc_enrich(jobs, state):
    """Hook: enrich Irish-matched jobs missing descriptions via public detail pages."""
    import desc_fetch
    global _detail_remaining
    nodesc = {j['key'] for j in jobs if not j.get('description')}
    result = desc_fetch.enrich_missing_descriptions(jobs, state, max_per_run=_detail_remaining, deadline=_detail_deadline)
    _detail_remaining = max(0, _detail_remaining - result[0] - result[1])
    for j in jobs:
        if j['key'] in nodesc and j.get('description'):
            j['description_state'] = 'PRESENT'
            j['context_candidate'] = bool(I.LANES.search(j['title'] + ' ' + j['description']))
    return result


I.desc_enricher = _desc_enrich
