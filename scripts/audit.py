import collections, re, sys
sys.path.insert(0, 'scripts')
from common import ROOT, CFG, load_offers, today

t = today().isoformat()
offers = load_offers()
print('== карточки в offers.json ==')
cnt = collections.Counter((o['source'], o.get('kind') or 'giveaway', o['status']) for o in offers)
for k, n in sorted(cnt.items()):
    print(' ', n, k)

print('\n== проверки согласованности ==')
FREE = ('бесплат', 'безкоштов', 'free', 'zadarmo', 'bezplat')
SPECIAL = ('demo', 'playtest', 'beta')
links = collections.Counter(o['link'] for o in offers)
bad = collections.defaultdict(list)
for o in offers:
    name = o['title'].get('ru', '')[:34]
    txt = ' '.join(str(v) for v in o['text'].values()).lower()
    if links[o['link']] > 1:
        bad['дубль ссылки'].append(name)
    if o['status'] == 'active' and o.get('expires_at') and o['expires_at'] < t:
        bad['активна, но срок прошёл'].append(name)
    if o.get('kind') == 'deal' and any(w in txt for w in FREE):
        bad['скидка названа бесплатной'].append(name)
    if o.get('kind') != 'deal' and o['source'] in ('epic-games', 'gamerpower') and not o.get('expires_at'):
        bad['раздача без срока'].append(name)
    if 'itch' in (o['link'] + name).lower() and (o.get('worth') or 0) < CFG.get('min_worth', {}).get('itch', 9) and o.get('kind') not in SPECIAL:
        bad['itch.io дешевле порога или цена неизвестна'].append(name)
    if re.search(r'\b(dlc|pack|bundle|soundtrack|season pass)\b', o['title'].get('en', '').lower()) and o.get('kind') not in SPECIAL:
        bad['похоже на DLC или набор'].append(name)
    if any(not o['text'].get(l) or not o['title'].get(l) for l in ('uk', 'ru', 'en', 'sk')):
        bad['нет текста на одном из языков'].append(name)
    if any('\n' in str(v) for v in o['text'].values()):
        bad['перенос строки в тексте'].append(name)
    if any(len(str(v)) > 330 for v in o['text'].values()):
        bad['текст длиннее 330 знаков'].append(name)
if not bad:
    print('  замечаний нет')
for k, v in bad.items():
    print('  ⚠', k, '|', sorted(set(v)))

print('\n== логи ==')
for name in ('pipeline.log', 'live.log', 'digest.log', 'review.log', 'report.log'):
    p = ROOT / 'logs' / name
    if p.exists():
        lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
        tail = lines[-300:]
        print(' ', name, '| строк', len(lines), '| 429:', sum('429' in l for l in tail), '| ошибок LLM:', sum('LLM' in l for l in tail), '| сбоев:', sum('Traceback' in l for l in tail))
        for l in lines[-2:]:
            print('     ', l[:140])
    else:
        print(' ', name, 'нет файла')

if '--live' in sys.argv:
    from api_sources import FETCHERS
    print('\n== источники (живые запросы) ==')
    for name, fn in FETCHERS.items():
        try:
            items = fn()
        except Exception as e:
            print(' ', name, '| ОШИБКА:', str(e)[:120])
            continue
        print(' ', name, '|', len(items), '| примеры:', [x['title'][:22] for x in items[:3]])
        free_deal = [x['title'][:22] for x in items if x.get('kind') == 'deal' and x.get('saved', 0) >= x.get('worth', 1)]
        if free_deal:
            print('     ⚠ «скидка» 100%, это раздача:', free_deal)
        if name in ('epic-games', 'gamerpower'):
            nod = [x['title'][:22] for x in items if not x.get('expires_at')]
            if nod:
                print('     ⚠ без срока:', nod)
