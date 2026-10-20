import html, json, re, yaml, feedparser
from urllib.parse import urlparse
from common import ROOT, offer_id, load_offers

SEEN = ROOT / 'data' / 'seen.json'
SKIP_HOSTS = ('reddit.com', 'redd.it', 'redditmedia.com', 'redditstatic.com')

def load_seen():
    if SEEN.exists():
        return set(json.loads(SEEN.read_text()))
    return set()

def mark_seen(ids):
    SEEN.write_text(json.dumps(sorted(load_seen() | set(ids))))

def external_link(entry_link, summary):
    for href in re.findall(r'href=["\']([^"\']+)["\']', summary):
        href = html.unescape(href)
        host = urlparse(href).netloc.lower()
        if href.startswith('http') and not any(host == h or host.endswith('.' + h) for h in SKIP_HOSTS):
            return href
    return entry_link

def link_key(url):
    p = urlparse(url)
    host = p.netloc.lower()
    if host.endswith('.itch.io'):
        return host
    return host + p.path.rstrip('/')

def clean(raw):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(raw))).strip()

def collect():
    existing = load_offers()
    seen = load_seen() | {o['id'] for o in existing}
    keys = {link_key(o['link']) for o in existing}
    found = {}
    cfg = yaml.safe_load((ROOT / 'sources.yaml').read_text(encoding='utf-8'))
    for s in cfg['sources']:
        feed = feedparser.parse(s['url'], agent='Mozilla/5.0 (kosice-offers-bot)')
        for e in feed.entries:
            link = e.get('link')
            if not link:
                continue
            i = offer_id(link)
            if i in seen or i in found:
                continue
            raw = e.get('summary', '')
            target = external_link(link, raw)
            k = link_key(target)
            if k in keys:
                continue
            keys.add(k)
            found[i] = {'id': i, 'title': e.get('title', ''), 'summary': clean(raw)[:1500], 'link': target, 'source': s['name']}
    return list(found.values())

if __name__ == '__main__':
    items = collect()
    print('новых находок:', len(items))
    for it in items[:5]:
        print('-', it['title'][:50], '->', it['link'])
