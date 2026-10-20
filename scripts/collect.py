import json, yaml, feedparser
from common import ROOT, offer_id, load_offers

SEEN = ROOT / 'data' / 'seen.json'

def load_seen():
    if SEEN.exists():
        return set(json.loads(SEEN.read_text()))
    return set()

def mark_seen(ids):
    SEEN.write_text(json.dumps(sorted(load_seen() | set(ids))))

def collect():
    seen = load_seen() | {o['id'] for o in load_offers()}
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
            found[i] = {'id': i, 'title': e.get('title', ''), 'summary': e.get('summary', '')[:1500], 'link': link, 'source': s['name']}
    return list(found.values())

if __name__ == '__main__':
    print('новых находок:', len(collect()))
