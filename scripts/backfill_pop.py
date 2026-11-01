import json, re, sys
sys.path.insert(0, 'scripts')
from common import ROOT, load_offers
from popularity import signals
from steam_signal import steam_signal

def name(t):
    return re.split(r' (бесплатно|вышла|вийшла|безкоштовно)', t)[0].strip()

def probe(title, link):
    s = signals({'title': title + ' itch.io', 'link': link, 'summary': ''})
    s.update(steam_signal(name(title)))
    return {k: s.get(k) for k in ('rating', 'ratings', 'steam_reviews', 'steam_pct')}

rej = [json.loads(l) for l in (ROOT / 'data' / 'rejects.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
print('== ОТКЛОНЕНО тобой ==')
for r in rej:
    print(r['reason'][:10], '| qa', r['score'], '| цена', r.get('worth'), '|', name(r['title'])[:28], '|', probe(name(r['title']), r['link']))
print('\n== ОПУБЛИКОВАНО (itch.io) ==')
for o in load_offers():
    t = o['title'].get('ru', '')
    if o['status'] == 'active' and 'itch' in (t + o['link']).lower():
        print('qa', o['score'], '| цена', o.get('worth'), '|', name(t)[:28], '|', probe(t, o['link']))
