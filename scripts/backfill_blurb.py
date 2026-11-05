import re, sys, time
sys.path.insert(0, 'scripts')
from common import load_offers, update_offers
from blurb import make_blurb
from chartdeals import desc_of
from epicdeals import fetch_epic_deals
from api_sources import fetch_epic, fetch_gamerpower

redo = '--redo' in sys.argv
only = sys.argv[sys.argv.index('--only') + 1].lower().split(',') if '--only' in sys.argv else None
descs = {}
for fn in (lambda: fetch_epic_deals(ttl=0), fetch_epic, fetch_gamerpower):
    try:
        for x in fn():
            descs[x['link']] = x.get('desc')
    except Exception as e:
        print('сбой источника:', str(e)[:80])
res, failed = {}, set()
for o in load_offers():
    if o.get('blurb') and not redo:
        continue
    if only and not any(s.strip() in (o['title']['en'] + ' ' + o['title']['ru']).lower() for s in only):
        continue
    d = descs.get(o['link'])
    m = re.search(r'/app/(\d+)/', o['link'])
    if not d and m:
        d = desc_of(int(m.group(1)))
        time.sleep(1)
    game = (o.get('deal') or o.get('give') or {}).get('game') or o['title']['en']
    b = make_blurb(game, d)
    print(game[:28], '->', (b or {}).get('uk', 'нет реплики'))
    if '--show' in sys.argv:
        print('      описание:', (d or '')[:230])
    if b:
        res[o['id']] = b
    else:
        failed.add(o['id'])

def apply(items):
    for o in items:
        if o['id'] in res:
            o['blurb'] = res[o['id']]
        elif redo and o['id'] in failed:
            o.pop('blurb', None)

update_offers(apply)
print('реплик:', len(res), '| без реплики:', len(failed))
