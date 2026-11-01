import collections, json, statistics, sys
sys.path.insert(0, 'scripts')
from common import ROOT, load_offers

def rows(name):
    p = ROOT / 'data' / name
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]

offers = load_offers()
snap = ROOT / 'data' / 'reactions_snapshot.json'
react = json.loads(snap.read_text(encoding='utf-8')) if snap.exists() else {}
print('== карточки по убыванию оценки QA ==')
for o in sorted(offers, key=lambda x: -x['score']):
    print(o['status'][:3], o['score'], o['source'][:10], 'цена', o.get('worth'), 'поп', o.get('pop'), '|', o['title'].get('ru', '')[:40], '|', react.get(o['id'], ''))
sc = [o['score'] for o in offers]
if sc:
    print('оценки: мин', min(sc), 'медиана', statistics.median(sc), 'макс', max(sc))
rej = rows('rejects.jsonl')
print('\n== твои отказы:', len(rej), '==')
print(collections.Counter(r['reason'] for r in rej))
for r in rej[-10:]:
    print(r['reason'], '|', r['score'], r.get('worth'), '|', r['title'][:40])
auto = rows('auto_rejects.jsonl')
print('\n== автоотказы:', len(auto), '==')
print(collections.Counter(a['why'].split(':')[0].split(' (')[0][:30] for a in auto).most_common(8))
