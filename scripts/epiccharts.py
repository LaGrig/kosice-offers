import time, requests
from common import CFG
from epicdeals import fetch_epic_deals

H = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}

def top_sellers_ids(n=100):
    ids, page = {}, 1
    while len(ids) < n and page <= 30:
        r = requests.get('https://api.egdata.app/offers/top-sellers', params={'page': page, 'limit': 50}, headers=H, timeout=25)
        r.raise_for_status()
        els = r.json().get('elements') or []
        if not els:
            break
        for e in els:
            if e.get('id') and e['id'] not in ids and len(ids) < n:
                ids[e['id']] = len(ids) + 1
        page += 1
        time.sleep(0.5)
    return ids

def epic_chart_deals():
    ranks = top_sellers_ids(CFG.get('deals', {}).get('chart_top', 100))
    out = []
    for it in fetch_epic_deals():
        rk = ranks.get(it.get('epic_id'))
        if rk:
            it = dict(it)
            it['chart_rank'] = rk
            it['deal'] = dict(it.get('deal') or {}, rank_sales=rk)
            it['source'] = 'epic-charts'
            it['summary'] = it['summary'].replace('. Цена', '. Игра сейчас в топ-' + str(rk) + ' по продажам в Epic Games Store. Цена', 1)
            out.append(it)
    out.sort(key=lambda x: x['chart_rank'])
    return out
