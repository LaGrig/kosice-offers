import json, re, time
from common import ROOT, CFG, load_offers, update_offers
from chartdeals import prices, info, top_played, top_sellers
from epicdeals import fetch_epic_deals
from epiccharts import top_sellers_ids
from dealtext import deal_post

LOG = ROOT / 'data' / 'removed.jsonl'

def steam_refresh(cards, c):
    cc = c.get('region', 'ua')
    apps = {}
    for o in cards:
        m = re.search(r'/app/(\d+)/', o['link'])
        if m:
            apps[int(m.group(1))] = o
    if not apps:
        return {}
    po = prices(list(apps), cc)
    try:
        n = c.get('chart_top', 100)
        played, sellers = top_played(n), top_sellers(n, cc)
    except Exception as e:
        print('Steam: рейтинги недоступны, места не обновляются:', str(e)[:80])
        played = sellers = None
    fresh = {}
    for app, o in apps.items():
        p = po.get(app)
        if not p or p.get('discount_percent', 0) < c.get('chart_min_savings', 70):
            continue
        old = o.get('deal') or {}
        name = old.get('game')
        if not name:
            try:
                name = info(app)[0]
                time.sleep(1)
            except Exception:
                name = None
        if not name:
            continue
        d = {'game': name, 'pct': p['discount_percent'], 'old': p.get('initial_formatted', ''), 'new': p.get('final_formatted', ''), 'store': 'Steam'}
        if played is None:
            d['rank_sales'], d['rank_play'] = old.get('rank_sales'), old.get('rank_play')
        else:
            d['rank_sales'], d['rank_play'] = sellers.get(app), played.get(app)
        fresh[o['id']] = d
    return fresh

def epic_refresh(cards, c):
    items = {x['link']: x for x in fetch_epic_deals(ttl=3000)}
    try:
        ranks = top_sellers_ids(c.get('chart_top', 100))
    except Exception as e:
        print('Epic: рейтинг недоступен, место не обновляется:', str(e)[:80])
        ranks = None
    fresh = {}
    for o in cards:
        x = items.get(o['link'])
        if not x:
            continue
        d = dict(x['deal'])
        old = o.get('deal') or {}
        d['rank_sales'] = ranks.get(x.get('epic_id')) if ranks is not None else old.get('rank_sales')
        fresh[o['id']] = d
    return fresh

def main():
    c = CFG.get('deals', {})
    offers = load_offers()
    steam = [o for o in offers if o['source'] == 'steam-chart' and o['status'] in ('active', 'pending')]
    epic = [o for o in offers if o['source'] == 'epic-charts' and o['status'] in ('active', 'pending')]
    fresh, checked = {}, set()
    for cards, fn, label in ((steam, steam_refresh, 'Steam'), (epic, epic_refresh, 'Epic')):
        if not cards:
            continue
        try:
            fresh.update(fn(cards, c))
            checked |= {o['id'] for o in cards}
        except Exception as e:
            print(label + ': сбой проверки:', str(e)[:100])
    miss, gone = {}, {}
    for o in offers:
        if o['id'] not in checked:
            continue
        if o['id'] in fresh:
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
            d = fresh.get(o['id'])
            if d:
                o['deal'] = d
                p = deal_post({'deal': d})
                o['title'], o['text'] = p['title'], p['text']
            out.append(o)
        return out
    update_offers(apply)
    with open(LOG, 'a', encoding='utf-8') as f:
        for o in gone.values():
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'id': o['id'], 'title': o['title'].get('ru', ''), 'source': o['source'],
                                'link': o['link'], 'why': 'скидка не подтвердилась два часа подряд'}, ensure_ascii=False) + '\n')

main()
