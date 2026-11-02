import re, time
from common import CFG, load_offers, offer_id
from steam_signal import get_json

CHART_URL = 'https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/'
STORE = 'https://store.steampowered.com/api/appdetails'
SEARCH = 'https://store.steampowered.com/search/results/'

def top_played(n):
    r = get_json(CHART_URL, {})
    ranks = (r.get('response') or {}).get('ranks') or []
    return {int(x['appid']): int(x['rank']) for x in ranks[:n]}

def top_sellers(n, cc):
    out, start = {}, 0
    while len(out) < n and start < 200:
        r = get_json(SEARCH, {'query': '', 'start': start, 'count': 50, 'filter': 'topsellers', 'cc': cc, 'infinite': 1, 'category1': 998})
        ids = [int(x) for x in re.findall(r'data-ds-appid="(\d+)"', r.get('results_html', ''))]
        if not ids:
            break
        for a in ids:
            if a not in out and len(out) < n:
                out[a] = len(out) + 1
        start += 50
        time.sleep(1)
    return out

def prices(appids, cc):
    out = {}
    ids = list(appids)
    for i in range(0, len(ids), 40):
        r = get_json(STORE, {'appids': ','.join(str(a) for a in ids[i:i + 40]), 'filters': 'price_overview', 'cc': cc})
        for k, v in r.items():
            d = v.get('data') if isinstance(v, dict) else None
            if isinstance(d, dict) and d.get('price_overview'):
                out[int(k)] = d['price_overview']
        time.sleep(1.5)
    return out

def info(app):
    r = get_json(STORE, {'appids': app, 'l': 'english', 'cc': 'us', 'filters': 'basic'})
    d = (r.get(str(app)) or {}).get('data')
    d = d if isinstance(d, dict) else {}
    return d.get('name'), d.get('type')

def _reviews_steam(app):
    r = get_json('https://store.steampowered.com/appreviews/' + str(app), {'json': 1, 'language': 'all', 'purchase_type': 'all'})
    s = r.get('query_summary') or {}
    pos, neg = s.get('total_positive', 0), s.get('total_negative', 0)
    return (pos + neg, round(100 * pos / (pos + neg))) if pos + neg else (0, 0)

def reviews(app):
    try:
        n, pct = _reviews_steam(app)
        if n:
            return n, pct
    except Exception:
        pass
    try:
        import requests
        rows = requests.get('https://www.cheapshark.com/api/1.0/deals', params={'steamAppID': app, 'pageSize': 1},
                            headers={'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}, timeout=25).json()
        if rows:
            return int(float(rows[0].get('steamRatingCount') or 0)), int(float(rows[0].get('steamRatingPercent') or 0))
    except Exception:
        pass
    return 0, 0

def chart_deals():
    c = CFG.get('deals', {})
    cc = c.get('region', 'ua')
    country = {'ua': 'Украине', 'sk': 'Словакии'}.get(cc, 'вашем регионе')
    n_top = c.get('chart_top', 100)
    played = top_played(n_top)
    sellers = top_sellers(n_top, cc)
    apps = sorted(set(played) | set(sellers))
    po = prices(apps, cc)
    out = []
    for app in apps:
        p = po.get(app)
        if not p or p.get('final', 0) <= 0 or p.get('discount_percent', 0) < c.get('chart_min_savings', 70):
            continue
        try:
            name, typ = info(app)
        except Exception:
            continue
        time.sleep(1)
        if typ != 'game' or not name:
            continue
        n, pct = reviews(app)
        time.sleep(1)
        rp, rs = played.get(app), sellers.get(app)
        parts = []
        if rs:
            parts.append('в топ-' + str(rs) + ' по продажам')
        if rp:
            parts.append('в топ-' + str(rp) + ' по онлайну')
        link = 'https://store.steampowered.com/app/' + str(app) + '/'
        summary = ('Steam: скидка ' + str(p['discount_percent']) + '% на игру ' + name + '. Игра сейчас ' + ' и '.join(parts) + ' в Steam. Цена в '
                   + country + ' была ' + p.get('initial_formatted', '') + ', стала ' + p.get('final_formatted', '') + '. '
                   + ('Оценки Steam: ' + str(pct) + '% положительных из ' + str(n) + ' отзывов. ' if n else '') + 'Срок окончания скидки в данных не указан.')
        out.append({'id': offer_id(link + '|' + str(p['final'])), 'title': name, 'summary': summary, 'link': link, 'source': 'steam-chart',
                    'expires_at': None, 'worth': p['initial'] / 100, 'kind': 'deal', 'store': 'Steam', 'steam_app': str(app),
                    'steam_pct': pct, 'steam_reviews': n, 'metacritic': 0, 'saved': (p['initial'] - p['final']) / 100,
                    'chart_rank': min(x for x in (rp, rs) if x)})
    out.sort(key=lambda x: x['chart_rank'])
    return out

def chart_live():
    c = CFG.get('deals', {})
    apps = {}
    for o in load_offers():
        if o['source'] == 'steam-chart':
            m = re.search(r'/app/(\d+)/', o['link'])
            if m:
                apps[int(m.group(1))] = o['link']
    if not apps:
        return set()
    po = prices(apps, c.get('region', 'ua'))
    return {link for a, link in apps.items() if po.get(a, {}).get('discount_percent', 0) >= c.get('chart_min_savings', 70)}
