import json, time, requests
from common import CFG, ROOT
from epicdeals import fetch_epic_deals

H = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}
CACHE = ROOT / 'data' / 'epic_ranks_cache.json'

def _fetch_page(page):
    for attempt in range(3):
        try:
            r = requests.get('https://api.egdata.app/offers/top-sellers',
                             params={'page': page, 'limit': 50}, headers=H, timeout=25)
            r.raise_for_status()
            if not r.text.strip():
                raise ValueError('empty body')
            return r.json().get('elements') or []
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def top_sellers_ids(n=100, ttl=3 * 3600):
    if CACHE.exists():
        try:
            d = json.loads(CACHE.read_text(encoding='utf-8'))
            if time.time() - d.get('ts', 0) < ttl and d.get('ids'):
                return {k: v for k, v in d['ids'].items() if v <= n}
        except Exception:
            pass
    ids, page = {}, 1
    try:
        while len(ids) < n and page <= 30:
            els = _fetch_page(page)
            if not els:
                break
            for e in els:
                if e.get('id') and e['id'] not in ids and len(ids) < n:
                    ids[e['id']] = len(ids) + 1
            page += 1
            time.sleep(0.5)
    except Exception:
        if len(ids) < 50:
            if CACHE.exists():
                try:
                    d = json.loads(CACHE.read_text(encoding='utf-8'))
                    if time.time() - d.get('ts', 0) < 12 * 3600 and d.get('ids'):
                        return {k: v for k, v in d['ids'].items() if v <= n}
                except Exception:
                    pass
            raise
    if ids:
        CACHE.write_text(json.dumps({'ts': time.time(), 'ids': ids}), encoding='utf-8')
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
