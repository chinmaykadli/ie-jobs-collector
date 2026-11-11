"""Bounded public-sitemap agency collector, copy-only, no production wiring.
State is per agency and persisted by the caller's immutable-generation mechanism.
"""
import json,re,time,xml.etree.ElementTree as ET,gzip
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import bounded_http
from agency_safe import update
JOBRE=re.compile(r'/(jobs?|vacanc\w*|job-details?|positions?)/[^/?#]+',re.I)
SKIP=re.compile(r'/discipline/|/jobs/(sector|specialism|in-)|/(jobs?|vacancies)/(contract|permanent|temporary|city|send-us|local-jobs|job-roles|[a-z-]+-jobs/?$)|/uk/|/(de|fr|es|ja-jp|en-gb|en-us)/',re.I)
def source_url(url,domain):
 u=urlsplit(url);host=(u.hostname or'').lower()
 if u.scheme!='https'or host not in(domain,'www.'+domain)or u.username or u.password or u.port not in(None,443):raise ValueError('URL outside explicit agency domain')
 query=urlencode([(k,v)for k,v in parse_qsl(u.query,keep_blank_values=True)if not k.lower().startswith('utm_')and k.lower()not in('gclid','fbclid')])
 return urlunsplit(('https',domain,u.path,query,''))
def text_fetch(url,domain):
 url=source_url(url,domain)
 with bounded_http.urlopen(url,max_bytes=4*1024*1024,total_seconds=20,timeout=10)as r:
  final=urlsplit(r.geturl());initial=urlsplit(url)
  if (final.hostname.removeprefix('www.'),final.path.rstrip('/'),final.query)!=(initial.hostname.removeprefix('www.'),initial.path.rstrip('/'),initial.query):raise ValueError('Changed resource redirect')
  b=r.read()
  # Some sitemap files use gzip without Content-Encoding. Reject rather than guess.
  if b[:2]==b'\x1f\x8b':raise ValueError('Undeclared compressed sitemap unsupported')
  return b.decode('utf-8',errors='strict')
def crawl(source,fetcher=None,max_maps=16,max_urls=30000,seconds=120):
 domain=source['domain'];fetcher=fetcher or(lambda u:text_fetch(u,domain));todo=list(source['sitemaps']);seen=set();urls=set();errors=[];off_domain_urls=0;start=time.monotonic()
 while todo and len(seen)<max_maps and time.monotonic()-start<seconds:
  original=todo.pop(0)
  if original in seen:continue
  seen.add(original)
  try:
   u=source_url(original,domain);text=fetcher(u)
   if len(text.encode())>4*1024*1024 or '<!DOCTYPE'in text.upper()or'<!ENTITY'in text.upper():raise ValueError('Unsafe/oversized sitemap')
   root=ET.fromstring(text);kind=root.tag.rsplit('}',1)[-1]
   if kind not in('sitemapindex','urlset'):raise ValueError('Unexpected sitemap root')
   namespace='http://www.sitemaps.org/schemas/sitemap/0.9'
   for entry in root:
    entry_kind=entry.tag.rsplit('}',1)[-1]
    if entry_kind not in('url','sitemap'):continue
    for el in entry:
     if el.tag not in('loc','{'+namespace+'}loc')or not el.text:continue
     try:link=source_url(el.text.strip(),domain)
     except ValueError:
      if kind=='sitemapindex':errors.append({'url':el.text.strip(),'error':'ChildSitemapOutsideDomain'})
      else:off_domain_urls+=1
      continue
     if kind=='sitemapindex':
      if link not in seen and link not in todo:todo.append(link)
     elif JOBRE.search(link)and not SKIP.search(link):urls.add(link)
     if len(urls)>max_urls:raise ValueError('Sitemap URL cap exceeded')
  except Exception as e:errors.append({'url':original,'error':type(e).__name__})
 complete=not todo and not errors and len(urls)<=max_urls
 return sorted(urls)[:max_urls],{'complete':complete,'maps_attempted':len(seen),'remaining_maps':len(todo),'errors':errors,'off_domain_urls':off_domain_urls}
def cycle(source,state,fetcher=None,max_details=25,now=None,**limits):
 urls,health=crawl(source,fetcher,**limits);domain=source['domain'];fetcher=fetcher or(lambda u:text_fetch(u,domain))
 state,details=update(state,domain,urls,health['complete'],fetcher,now=now,max_details=max_details)
 return state,{'source':domain,'sitemap':health,'details':details,'discovered_urls':len(urls)}
