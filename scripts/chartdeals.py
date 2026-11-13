import requests
import datetime as dt
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
    except Exception as e:
        print("deal_expires err:", app, e)
    try:
        import requests
        rows = requests.get('https://www.cheapshark.com/api/1.0/deals', params={'steamAppID': app, 'pageSize': 1},
                            headers={'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}, timeout=25).json()
        if rows:
            return int(float(rows[0].get('steamRatingCount') or 0)), int(float(rows[0].get('steamRatingPercent') or 0))
    except Exception as e:
        print("deal_expires err:", app, e)
    return 0, 0

def desc_of(app):
    try:
        r = get_json(STORE, {'appids': app, 'l': 'english', 'cc': 'us', 'filters': 'basic'})
        d = (r.get(str(app)) or {}).get('data')
        return (d.get('short_description') or '')[:400] if isinstance(d, dict) else ''
    except Exception:
        return ''

_MONTHS = {
    'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
    'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12,
}

def deal_expires(app, cc='ua'):
    try:
        r = requests.get(
            f'https://store.steampowered.com/app/{app}/',
            params={'cc': cc, 'l': 'english'},
            cookies={'birthtime': '568022401', 'wants_mature_content': '1'},
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        html = r.text
        m_ts = re.search(r'InitDiscountCountdown\([^,]+,\s*(\d+)', html)
        if m_ts:
            return dt.datetime.fromtimestamp(int(m_ts.group(1)), dt.timezone.utc).date().isoformat()
        for raw in re.findall(r'class="game_purchase_discount_countdown"[^>]*>(.*?)</p>', html, re.S):
            txt = re.sub(r'<[^>]+>', ' ', raw)
            txt = re.sub(r'\s+', ' ', txt).strip()
            m1 = re.search(r'Offer ends\s+(\d{1,2})\s+([A-Za-z]+)', txt, re.I)
            m2 = re.search(r'Offer ends\s+([A-Za-z]+)\s+(\d{1,2})', txt, re.I)
            if m1:
                day, mon_s = int(m1.group(1)), m1.group(2).lower()
            elif m2:
                mon_s, day = m2.group(1).lower(), int(m2.group(2))
            else:
                continue
            mon = _MONTHS.get(mon_s)
            if not mon:
                continue
            today_d = dt.date.today()
            yr = today_d.year
            try:
                cand = dt.date(yr, mon, day)
            except ValueError:
                continue
            if (today_d - cand).days > 30:
                cand = dt.date(yr + 1, mon, day)
            return cand.isoformat()
    except Exception as e:
        print("deal_expires err:", app, e)
    return None

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
        exp = deal_expires(app, cc)
        time.sleep(1)
        out.append({'id': offer_id(link + '|' + str(p['final'])), 'title': name, 'summary': summary, 'link': link, 'source': 'steam-chart',
                    'expires_at': exp, 'worth': p['initial'] / 100, 'kind': 'deal', 'store': 'Steam', 'steam_app': str(app),
                    'steam_pct': pct, 'steam_reviews': n, 'metacritic': 0, 'saved': (p['initial'] - p['final']) / 100,
                    'chart_rank': min(x for x in (rp, rs) if x), 'desc': desc_of(app),
                    'deal': {'game': name, 'pct': p['discount_percent'], 'old': p.get('initial_formatted', ''), 'new': p.get('final_formatted', ''), 'store': 'Steam', 'rank_sales': rs, 'rank_play': rp}})
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
