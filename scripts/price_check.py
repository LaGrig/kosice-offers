import json, time
from common import ROOT, load_offers, update_offers
from chartdeals import chart_live
from epicdeals import fetch_epic_deals

LOG = ROOT / 'data' / 'removed.jsonl'

def main():
    offers = load_offers()
    steam = [o for o in offers if o['source'] == 'steam-chart' and o['status'] in ('active', 'pending')]
    epic = [o for o in offers if o['source'] == 'epic-charts' and o['status'] in ('active', 'pending')]
    live, checked = set(), set()
    try:
        if steam:
            live |= set(chart_live())
            checked |= {o['id'] for o in steam}
    except Exception as e:
        print('Steam: сбой проверки:', str(e)[:100])
    try:
        if epic:
            live |= {x['link'] for x in fetch_epic_deals(ttl=3000)}
            checked |= {o['id'] for o in epic}
    except Exception as e:
        print('Epic: сбой проверки:', str(e)[:100])
    miss, gone = {}, {}
    for o in offers:
        if o['id'] not in checked:
            continue
        if o['link'] in live:
            miss[o['id']] = 0
        else:
            miss[o['id']] = o.get('miss_p', 0) + 1
            if miss[o['id']] >= 2:
                gone[o['id']] = o
                print('скидка закончилась:', o['id'], o['title'].get('ru', ''))
    def apply(cur):
        out = []
        for o in cur:
            if o['id'] in gone:
                continue
            if o['id'] in miss:
                o['miss_p'] = miss[o['id']]
            out.append(o)
        return out
    update_offers(apply)
    with open(LOG, 'a', encoding='utf-8') as f:
        for o in gone.values():
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'id': o['id'], 'title': o['title'].get('ru', ''), 'source': o['source'],
                                'link': o['link'], 'why': 'скидка не подтвердилась два часа подряд'}, ensure_ascii=False) + '\n')

main()
