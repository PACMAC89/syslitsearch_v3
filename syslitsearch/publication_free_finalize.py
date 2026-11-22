"""Zero-paid-API, bounded official-site evidence discovery and final reading-list export.

Does not certify peer review. Never uses paid search, LLMs, or paper PDFs.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

KEYWORDS = ('peer review', 'peer-review', 'peer reviewed', 'peer-reviewed', 'review process',
            'reviewing process', 'editorial policy', 'author guidelines',
            'instructions for authors', 'call for papers', 'submission guidelines',
            'review criteria', 'double blind', 'double-blind', 'single blind', 'single-blind')
HEADERS = ('Group ID','Venue','Type','ISSN','Paper IDs','Paper count','Source URL',
           'Candidate URL','Candidate title','Matched phrases','Evidence excerpt',
           'Fetch status','HTTP status','Retrieved UTC','Content SHA256','Scope warning')
DENY_HOSTS = ('localhost','127.0.0.1','0.0.0.0','169.254.169.254','metadata.google.internal')

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.skip=0;self.title=False;self.titles=[];self.text=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style','noscript'):self.skip+=1
        if tag=='title':self.title=True
        if tag=='a' and attrs.get('href'):
            self.links.append((attrs['href'],attrs.get('title','')))
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
        if tag=='title':self.title=False
    def handle_data(self,data):
        if self.title:self.titles.append(data)
        if not self.skip:self.text.append(data)

def valid_url(url):
    try:
        p=urlparse(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password:return False
        host=p.hostname.lower()
        if host in DENY_HOSTS or host.endswith('.local') or host.endswith('.internal'):return False
        # Reject literal IPs (including IPv6) to avoid fetching private-network resources.
        import ipaddress
        try:ipaddress.ip_address(host);return False
        except ValueError:pass
        return True
    except ValueError:return False

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f);rows=list(r)
        if not {'ID','Paper fingerprint'}.issubset(r.fieldnames or []):
            raise ValueError('Missing ID or Paper fingerprint: '+str(path))
    if len({r['ID'] for r in rows})!=len(rows):raise ValueError('Duplicate IDs: '+str(path))
    return rows

def fetch(url, cache_dir, session, timeout, offline):
    key=hashlib.sha256(url.encode()).hexdigest();path=cache_dir/(key+'.json')
    if path.exists():
        try:return json.loads(path.read_text(encoding='utf-8')),False
        except (ValueError,OSError):pass
    if offline:return {'status':'not_cached'},False
    try:
        # Explicitly disallow redirects: avoid untrusted off-domain/private-network redirects.
        resp=session.get(url,timeout=timeout,allow_redirects=False,stream=True)
        if 300<=resp.status_code<400:
            result={'status':'redirect_not_followed','http':resp.status_code,
                    'redirect_url':urljoin(url,resp.headers.get('Location',''))}
        elif resp.status_code!=200:
            result={'status':'http_error','http':resp.status_code}
        elif 'text/html' not in resp.headers.get('Content-Type','').lower():
            result={'status':'not_html','http':resp.status_code}
        else:
            chunks=[];size=0
            for chunk in resp.iter_content(16384):
                size+=len(chunk)
                if size>750_000:break
                chunks.append(chunk)
            if size>750_000:result={'status':'too_large','http':resp.status_code}
            else:
                raw=b''.join(chunks);page=Page();page.feed(raw.decode(resp.encoding or 'utf-8',errors='replace'))
                result={'status':'ok','http':resp.status_code,'title':' '.join(page.titles)[:200],
                        'text':' '.join(' '.join(page.text).split())[:60000],
                        'links':page.links[:400],'sha256':hashlib.sha256(raw).hexdigest(),
                        'retrieved':datetime.now(timezone.utc).isoformat()}
        resp.close()
    except requests.RequestException as exc:
        result={'status':'fetch_error','error':type(exc).__name__}
    path.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result,True

def run(metadata, output, *, max_groups=200, max_pages=120, timeout=12, delay=.4,
        offline=False, cache_dir=None, session=None):
    metadata=Path(metadata);output=Path(output)
    if output.exists():raise FileExistsError('Refusing to overwrite '+str(output))
    if max_groups<1 or max_pages<0 or timeout<=0 or delay<0:raise ValueError('Invalid limits')
    md=read_csv(metadata)
    groups=defaultdict(list)
    for m in md:
        venue=(m.get('Crossref venue') or m.get('OpenAlex venue') or '').strip()
        typ=(m.get('Crossref type') or m.get('OpenAlex type') or '').strip()
        issn=(m.get('Crossref ISSN') or '').strip()
        # For conference series, year/track not reliably present in metadata.
        # Group for discovery only, never propagate certification across group.
        key=(venue.casefold() if venue else 'missing:'+m['ID'],typ.casefold(),issn.casefold())
        groups[key].append(m)
    cache_dir=Path(cache_dir or output.parent/'free_policy_cache');cache_dir.mkdir(parents=True,exist_ok=True)
    session=session or requests.Session()
    session.headers.update({'User-Agent':'syslitsearch-free-evidence/1.0 (academic policy research)'})
    records=[];network=0;cache_hits=0;unique=set();groups_checked=0
    for key,members in sorted(groups.items(),key=lambda x:(-len(x[1]),x[0]))[:max_groups]:
        m=members[0];venue=(m.get('Crossref venue') or m.get('OpenAlex venue') or '').strip()
        typ=(m.get('Crossref type') or m.get('OpenAlex type') or '').strip()
        issn=(m.get('Crossref ISSN') or '').strip()
        base={'Group ID':hashlib.sha256(repr(key).encode()).hexdigest()[:14],
              'Venue':venue,'Type':typ,'ISSN':issn,
              'Paper IDs':';'.join(r['ID'] for r in members),'Paper count':len(members),
              'Scope warning':'Discovery only; journal/conference policy does NOT prove paper, year, track or contribution peer review'}
        if not venue:
            records.append({**base,'Fetch status':'missing_venue'});continue
        groups_checked+=1
        # The only starting points are DOI landing pages already in the stored metadata.
        # No search APIs, no LLM, no OpenAlex or Crossref API calls.
        starts=[]
        for r in members[:3]:
            for k in ('Crossref URL','OpenAlex URL'):
                u=(r.get(k) or '').strip()
                if valid_url(u) and u not in starts:starts.append(u)
        if not starts:
            records.append({**base,'Fetch status':'no_official_start_url'});continue
        candidates=[]
        for start in starts[:2]:
            candidates.append((start,'landing_page'))
        visited=set(); group_results=0
        for url,kind in candidates:
            if url in visited:continue
            visited.add(url)
            if url not in unique and network>=max_pages and not (cache_dir/(hashlib.sha256(url.encode()).hexdigest()+'.json')).exists():
                records.append({**base,'Source URL':url,'Fetch status':'request_limit'});continue
            result,called=fetch(url,cache_dir,session,timeout,offline)
            if called:network+=1;time.sleep(delay) if delay else None
            else:cache_hits+=1
            unique.add(url)
            status=result.get('status','unknown')
            records.append({**base,'Source URL':url,'Candidate URL':url,
                            'Candidate title':result.get('title',''),
                            'Fetch status':status,'HTTP status':result.get('http',''),
                            'Retrieved UTC':result.get('retrieved',''),'Content SHA256':result.get('sha256','')})
            if status=='redirect_not_followed':
                target=result.get('redirect_url','')
                if valid_url(target) and target not in visited and (network<max_pages or (cache_dir/(hashlib.sha256(target.encode()).hexdigest()+'.json')).exists()):
                    page,called=fetch(target,cache_dir,session,timeout,offline)
                    if called:network+=1;time.sleep(delay) if delay else None
                    else:cache_hits+=1
                    unique.add(target);visited.add(target)
                    records.append({**base,'Source URL':url,'Candidate URL':target,'Candidate title':page.get('title',''),
                                    'Fetch status':page.get('status','unknown'),'HTTP status':page.get('http',''),
                                    'Retrieved UTC':page.get('retrieved',''),'Content SHA256':page.get('sha256','')})
                    if page.get('status')=='ok':url=target;result=page;status='ok'
            if status!='ok':continue
            # Link discovery only on same domain as fetched source; never treat as official automatically.
            host=urlparse(url).hostname or ''
            links=[]
            for href,title in result.get('links',[]):
                target=urljoin(url,href)
                if valid_url(target) and urlparse(target).hostname==host and any(w in (href+' '+title).casefold() for w in
                    ('peer-review','peer_review','peerreview','review-process','review-policy','editorial','author','guideline','submission','call-for-papers')):
                    if target not in visited and target not in links:links.append(target)
            for target in links[:3]:
                if network>=max_pages and not (cache_dir/(hashlib.sha256(target.encode()).hexdigest()+'.json')).exists():break
                page,called=fetch(target,cache_dir,session,timeout,offline)
                if called:network+=1;time.sleep(delay) if delay else None
                else:cache_hits+=1
                unique.add(target);visited.add(target)
                text=page.get('text','');lower=text.casefold()
                terms=[term for term in KEYWORDS if term in lower]
                pos=min((lower.find(term) for term in terms),default=-1)
                excerpt=text[max(0,pos-180):pos+350] if pos>=0 else ''
                records.append({**base,'Source URL':url,'Candidate URL':target,
                                'Candidate title':page.get('title',''),'Matched phrases':';'.join(terms),
                                'Evidence excerpt':excerpt,'Fetch status':page.get('status','unknown'),
                                'HTTP status':page.get('http',''),'Retrieved UTC':page.get('retrieved',''),
                                'Content SHA256':page.get('sha256','')})
                group_results+=bool(terms)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(records)
    return {'papers':len(md),'groups_total':len(groups),'groups_processed':groups_checked,
            'network_requests':network,'cache_hits':cache_hits,'policy_text_candidates':sum(bool(r.get('Matched phrases')) for r in records),
            'certified':0,'output':str(output),'cost':'No paid API or LLM calls',
            'limitation':'Only one safe DOI redirect and same-domain policy links are inspected; many publisher pages may remain undiscovered'}

def main(argv=None):
    p=argparse.ArgumentParser(description='Zero-paid-API bounded official-site evidence discovery')
    p.add_argument('--metadata',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--max-groups',type=int,default=200)
    p.add_argument('--max-pages',type=int,default=120)
    p.add_argument('--timeout',type=int,default=12)
    p.add_argument('--delay',type=float,default=.4)
    p.add_argument('--offline',action='store_true')
    p.add_argument('--cache-dir',type=Path)
    a=p.parse_args(argv)
    try:print(json.dumps(run(a.metadata,a.out,max_groups=a.max_groups,max_pages=a.max_pages,
                             timeout=a.timeout,delay=a.delay,offline=a.offline,cache_dir=a.cache_dir),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as exc:p.error(str(exc))
if __name__=='__main__':main()
