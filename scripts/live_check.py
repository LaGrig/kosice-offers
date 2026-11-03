import json, time
from common import ROOT, load_offers, update_offers
from api_sources import live_by_source

LOG = ROOT / 'data' / 'removed.jsonl'

def main():
    live = live_by_source()
    miss, gone = {}, {}
    for o in load_offers():
        links = live.get(o['source'])
        if links is None or o['status'] not in ('active', 'pending'):
            continue
        if o['link'] in links:
            miss[o['id']] = 0
        else:
            miss[o['id']] = o.get('miss', 0) + 1
            if miss[o['id']] >= 2:
                gone[o['id']] = o
                print('раздача закончилась:', o['id'], o['title'].get('ru', ''))
    def apply(cur):
        out = []
        for o in cur:
            if o['id'] in gone:
                continue
            if o['id'] in miss:
                o['miss'] = miss[o['id']]
            out.append(o)
        return out
    update_offers(apply)
    with open(LOG, 'a', encoding='utf-8') as f:
        for o in gone.values():
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'id': o['id'], 'title': o['title'].get('ru', ''), 'source': o['source'],
                                'link': o['link'], 'why': 'нет в живой выдаче два раза подряд'}, ensure_ascii=False) + '\n')

main()
