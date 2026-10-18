"""Drop-in extension for ingest.py: smartrecruiters, workable, recruitee (plain GET) and workday (POST fetcher).
Does not replace ingest.py. `import ats_extra` patches ingest.normalize and ingest.pagination_evidence;
greenhouse/ashby/lever behaviour is untouched (original functions are called for them)."""
import json, urllib.request, urllib.error, re
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

def pagination_evidence(payload):
    if isinstance(payload, dict):
        if 'complete' in payload: return 'COMPLETE_EXPLICIT' if payload['complete'] else 'INCOMPLETE'
        if 'totalFound' in payload and isinstance(payload.get('content'), list):
            return 'COMPLETE_EXPLICIT' if payload['totalFound'] <= len(payload['content']) else 'INCOMPLETE'
    return _orig_page(payload)

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
            jid = (j.get('bulletFields') or [None])[0] or j.get('externalPath'); title = j.get('title')
            base = source['url'].split('/wday/')[0]; site = source['url'].split('/cxs/')[1].split('/')[1]
            url = base + '/' + site + j['externalPath'] if j.get('externalPath') else None
            loc = j.get('locationsText') or ''
            posted, dtype, desc, upd = j.get('postedOn'), 'relative_text_not_a_date', '', None
        if jid is None: raise ValueError('Job missing stable id')
        if not title: raise ValueError('Job missing title')
        if not url or not url.startswith('https://'): raise ValueError('Missing authoritative job link')
        ireland = I.irish_location(loc) and not (ats == 'smartrecruiters' and not (j.get('location') or {}).get('country')) and not re.search(r'\bnot stated\b', loc)
        nodesc = ats in ('smartrecruiters', 'workday', 'rippling') or not desc.strip()
        res.append({'key': '%s:%s:%s' % (ats, source['token'], jid), 'company': source['company'], 'ats': ats, 'id': str(jid), 'title': title, 'location': loc,
                    'irish_location_match': ireland, 'remote_ireland_eligibility_unverified': bool(I.remote_ireland_pending(loc, ireland)),
                    'context_candidate': bool(I.LANES.search(title + ' ' + desc)) and not nodesc, 'description_state': 'MISSING' if nodesc else 'PRESENT', 'coverage_scope': ('BOUNDED_SEARCH_IRELAND_NOT_GLOBAL' if ats == 'workday' else 'FULL_FEED_PAGINATION_PER_RECEIPT'), 'job_url': url, 'apply_url': None,
                    'source_posted_at': posted, 'source_posted_at_utc': I.posted_utc(posted, dtype) if dtype in ('releasedDate', 'published_at', 'first_published_at') else None,
                    'source_posted_at_original': posted, 'source_updated_at': upd, 'timestamp_semantics': dtype, 'employment_type': None,
                    'description': desc[:4000], 'review_state': 'NOT_REVIEWED', 'source_url': source['url']})
    return _merge_dupes(res)

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
    return out

I.normalize, I.pagination_evidence = normalize, pagination_evidence

def run(sources, out):
    """All sources, including Workday, go through ingest's own fetch, receipts and backoff path."""
    return I.ingest(sources, out)


def _desc_enrich(jobs, state):
    """Hook: enrich Irish-matched jobs missing descriptions via public detail pages."""
    import desc_fetch
    nodesc = {j['key'] for j in jobs if not j.get('description')}
    result = desc_fetch.enrich_missing_descriptions(jobs, state, max_per_run=500)
    for j in jobs:
        if j['key'] in nodesc and j.get('description'):
            j['context_candidate'] = bool(I.LANES.search(j['title'] + ' ' + j['description']))
    return result


I.desc_enricher = _desc_enrich
