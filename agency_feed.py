#!/usr/bin/env python3
"""Public-sitemap agency job feed. No logins. Writes out/agency-queue.json and state/agency-seen.json.
First pass: sitemap job URLs -> slug title -> lane filter -> detail fetch (JSON-LD or page text) -> Irish location test."""
import json, re, gzip, sys, time, html, pathlib, urllib.request, concurrent.futures as cf
import ingest as I
H = {'User-Agent': 'Mozilla/5.0 (compatible; ie-jobs-collector/1.0)'}
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 150
JOBRE = re.compile(r'/(jobs?|vacanc\w*|job-details?|positions?)/[^/?#]+', re.I)
SKIP = re.compile(r'/discipline/|/jobs/(sector|specialism|in-)|/(jobs?|vacancies)/(contract|permanent|temporary|city|send-us|local-jobs|job-roles|[a-z-]+-jobs/?$)|/uk/|/(de|fr|es|ja-jp|en-gb|en-us)/', re.I)
def get(u, t=15):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=t); b = r.read(2500000)
        if b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
        return b.decode('utf8', 'ignore')
    except Exception: return None
def locs(x): return re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', x or '')
def crawl(src):
    q = list(src['sitemaps']); seen = set(); urls = []; n = 0; err = 0
    while q and n < 16:
        u = q.pop(0)
        if u in seen: continue
        seen.add(u); n += 1; x = get(u)
        if x is None: err += 1; continue
        for l in locs(x):
            if re.search(r'\.xml(\?|$)|\.gz$', l):
                if re.search(r'job|vacanc|position|listing|sitemap', l, re.I): q.append(l)
            elif JOBRE.search(l) and not SKIP.search(l): urls.append(l)
    return src['domain'], sorted(set(urls)), err
def slug_title(u):
    s = u.rstrip('/').split('/')[-1]; s = re.sub(r'^\d+-|-\d+$|\.html?$', '', s)
    return s.replace('-', ' ')
def detail(u):
    h = get(u)
    if h is None: return None
    title = loc = desc = ''
    for m in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', h, re.S):
        if 'JobPosting' not in m: continue
        try: d = json.loads(m, strict=False)
        except Exception: continue
        if isinstance(d, list): d = next((x for x in d if x.get('@type') == 'JobPosting'), {})
        if '@graph' in d: d = next((g for g in d['@graph'] if g.get('@type') == 'JobPosting'), {})
        title = html.unescape(d.get('title') or ''); desc = re.sub(r'<[^>]+>', ' ', html.unescape(d.get('description') or ''))
        jl = d.get('jobLocation'); jl = jl[0] if isinstance(jl, list) and jl else jl
        a = (jl or {}).get('address', {}) if isinstance(jl, dict) else {}
        if isinstance(a, dict): loc = ', '.join(str(v if not isinstance(v, list) else ', '.join(v)) for v in [a.get('addressLocality'), a.get('addressRegion'), a.get('addressCountry') if isinstance(a.get('addressCountry'), str) else (a.get('addressCountry') or {}).get('name', '')] if v)
        break
    text = re.sub(r'\s+', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S)); text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    if not title:
        m = re.search(r'<title[^>]*>(.*?)</title>', h, re.S); title = html.unescape(m.group(1)).strip() if m else ''
    if not desc: desc = text[:6000]
    return {'title': title, 'location': loc, 'description': desc[:4000], 'page_text_head': text[:1500]}
def main():
    srcs = json.load(open('agency_sources.json')); sp = pathlib.Path('state/agency-seen.json')
    seen = json.load(open(sp)) if sp.exists() else {}
    hp = pathlib.Path('state/agency-hits.json'); hits = json.load(open(hp)) if hp.exists() else {}
    health = []; allurls = {}
    with cf.ThreadPoolExecutor(8) as ex:
        for dom, urls, err in ex.map(crawl, srcs):
            health.append({'source': dom, 'urls': len(urls), 'fetch_errors': err, 'status': 'OK_NONEMPTY' if urls else ('ERROR' if err else 'OK_ZERO')})
            for u in urls: allurls[u] = dom
    new = [u for u in allurls if u not in seen]
    cand = [u for u in new if I.LANES.search(slug_title(u))]
    todo = cand[:CAP]; out = []
    def work(u): return u, detail(u)
    with cf.ThreadPoolExecutor(8) as ex:
        for u, d in ex.map(work, todo):
            if d is None: continue  # retry next cycle
            seen[u] = {'first_seen': time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime()), 'detail': True}
            loc = d['location'] or ''
            irl = I.irish_location(loc) if loc else bool(I.irish_location(d['page_text_head'][:600]))
            if not irl and not re.search(r'\b(ireland|dublin|cork|galway|limerick|waterford|kilkenny|athlone|sligo|louth|drogheda|dundalk|meath|kildare|wicklow)\b', (loc + ' ' + d['page_text_head'][:500]), re.I): continue
            out.append({'key': 'agency:%s:%s' % (allurls[u], u.rstrip('/').split('/')[-1]), 'company': allurls[u] + ' (agency)', 'ats': 'agency-sitemap', 'title': d['title'] or slug_title(u), 'location': loc or 'Ireland (page text)', 'job_url': u, 'description': d['description'], 'review_state': 'NOT_REVIEWED'})
    for u in new:  # non-lane new URLs: mark seen without detail
        if u not in seen and u not in todo and not I.LANES.search(slug_title(u)): seen[u] = {'first_seen': time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime()), 'detail': False}
    newhits = [h for h in out if h['key'] not in hits]
    for h in out: hits.setdefault(h['key'], h)
    sp.parent.mkdir(exist_ok=True); json.dump(seen, open(sp, 'w')); json.dump(hits, open(hp, 'w'))
    pathlib.Path('out').mkdir(exist_ok=True)
    json.dump({'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'total_urls': len(allurls), 'new_urls': len(new), 'lane_candidates': len(cand), 'detail_fetched': len(todo), 'backlog_remaining': max(0, len(cand) - len(todo)), 'irish_lane_hits_this_run': len(newhits), 'irish_lane_hits_total': len(hits), 'source_health': health, 'queue_new_this_run': newhits}, open('out/agency-queue.json', 'w'), indent=1)
    print(len(allurls), len(new), len(cand), len(todo), len(newhits), len(hits))
main()
