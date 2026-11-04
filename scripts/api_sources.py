import re, time, datetime as dt, requests
from common import offer_id, CFG
from givefmt import give_info

UA = {'User-Agent': 'Mozilla/5.0 (kosice-offers-bot)'}
EPIC_COUNTRY = 'UA'
SKIPPED = []

def fetch_epic():
    r = requests.get('https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions',
                     params={'locale': 'en-US', 'country': EPIC_COUNTRY, 'allowCountries': EPIC_COUNTRY},
                     headers=UA, timeout=25)
    r.raise_for_status()
    out = []
    for e in r.json()['data']['Catalog']['searchStore']['elements']:
        promos = (e.get('promotions') or {}).get('promotionalOffers') or []
        if not promos or not promos[0].get('promotionalOffers'):
            continue
        price = (e.get('price') or {}).get('totalPrice') or {}
        if price.get('discountPrice') != 0 or not price.get('originalPrice'):
            continue
        slug = None
        for m in (e.get('offerMappings') or []) + ((e.get('catalogNs') or {}).get('mappings') or []):
            if m.get('pageSlug'):
                slug = m['pageSlug']
                break
        slug = slug or e.get('productSlug') or e.get('urlSlug')
        if not slug:
            continue
        link = 'https://store.epicgames.com/p/' + slug.replace('/home', '')
        end = promos[0]['promotionalOffers'][0]['endDate'][:10]
        if end < dt.date.today().isoformat():
            continue
        dec = (price.get('currencyInfo') or {}).get('decimals', 2)
        ow = price['originalPrice'] / (10 ** dec)
        if ow < CFG.get('epic_min_local', 400):
            SKIPPED.append({'id': offer_id(link), 'title': e.get('title', ''), 'summary': (e.get('description') or '')[:300],
                            'link': link, 'source': 'epic-games', 'expires_at': end, 'worth': ow,
                            'why': 'цена ' + str(ow) + ' ниже порога'})
            continue
        orig = (price.get('fmtPrice') or {}).get('originalPrice', '')
        summary = ('Epic Games Store: бесплатная раздача игры ' + e.get('title', '') + '. Обычная цена ' + orig
                   + '. Бесплатно до ' + end + ' (UTC). ' + (e.get('description') or '')[:300])
        out.append({'id': offer_id(link), 'title': e.get('title', ''), 'summary': summary,
                    'link': link, 'source': 'epic-games', 'expires_at': end, 'worth': ow,
                    'give': {'game': e.get('title', ''), 'store': 'Epic Games Store', 'price': orig, 'until': end},
                    'desc': (e.get('description') or '')[:400]})
    return out

def fetch_gamerpower():
    r = requests.get('https://www.gamerpower.com/api/giveaways',
                     params={'platform': 'pc', 'type': 'game'}, headers=UA, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out = []
    for g in data:
        if g.get('status') != 'Active':
            continue
        worth = g.get('worth') or 'N/A'
        if worth in ('N/A', '$0.00'):
            continue
        plats = g.get('platforms') or ''
        if 'Epic' in plats:
            continue
        link = g.get('open_giveaway_url') or g.get('gamerpower_url')
        if not link:
            continue
        if re.search(r'\b(dlc|pack|bundle|demo|soundtrack|season pass|upgrade|add-?on|playtest)\b', g.get('title', '').lower()):
            continue
        end = (g.get('end_date') or 'N/A')[:10]
        if re.match(r'^\d{4}-\d{2}-\d{2}$', end):
            note = 'до ' + end
        else:
            try:
                pub = (g.get('published_date') or '')[:10]
                end = (dt.date.fromisoformat(pub) + dt.timedelta(days=3)).isoformat()
            except ValueError:
                continue
            note = 'срок не указан (считаем 3 дня)'
        if end < dt.date.today().isoformat():
            continue
        try:
            wv = float(re.sub(r'[^0-9.]', '', worth) or 0)
        except ValueError:
            wv = 0
        low = (plats + ' ' + g.get('title', '')).lower()
        key = next((k for k in ('steam', 'gog', 'itch') if k in low), 'default')
        mw = CFG.get('min_worth', {})
        if wv < mw.get(key, mw.get('default', 15)):
            SKIPPED.append({'id': offer_id(link), 'title': g.get('title', ''), 'summary': plats + ' ' + worth + ' ' + (g.get('description') or '')[:300],
                            'link': link, 'source': 'gamerpower', 'expires_at': end, 'worth': wv, 'users': g.get('users'),
                            'why': 'цена ' + str(wv) + ' ниже порога (' + key + ')'})
            continue
        summary = (plats + ': бесплатная раздача ' + g.get('title', '') + ' (обычная цена ' + worth + '). Бесплатно '
                   + note + '. ' + (g.get('description') or '')[:300] + ' ' + (g.get('instructions') or '')[:300])
        out.append({'id': offer_id(link), 'title': g.get('title', ''), 'summary': summary,
                    'link': link, 'source': 'gamerpower', 'expires_at': end, 'worth': wv, 'users': g.get('users'),
                    'give': give_info(g, plats, worth, note, end),
                    'desc': (g.get('description') or '')[:400]})
    return out

DEAL_UA = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}

def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

def _fetch_deals_raw():
    c = CFG.get('deals', {})
    st = requests.get('https://www.cheapshark.com/api/1.0/stores', headers=DEAL_UA, timeout=25)
    st.raise_for_status()
    ids = {s['storeName']: s['storeID'] for s in st.json() if s.get('storeName') in ('Steam',)}
    out = []
    for name, sid in ids.items():
        for page in range(25):
            r = requests.get('https://www.cheapshark.com/api/1.0/deals',
                             params={'storeID': sid, 'onSale': 1, 'AAA': 1, 'sortBy': 'Deal Rating', 'pageSize': 60, 'pageNumber': page},
                             headers=DEAL_UA, timeout=25)
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            for d in rows:
                normal, sale, sav = _f(d.get('normalPrice')), _f(d.get('salePrice')), _f(d.get('savings'))
                if normal < c.get('min_normal', 25) or sav < c.get('min_savings', 70):
                    continue
                link = 'https://www.cheapshark.com/redirect?dealID=' + d['dealID']
                n, pct, mc = int(_f(d.get('steamRatingCount'))), int(_f(d.get('steamRatingPercent'))), int(_f(d.get('metacriticScore')))
                app = d.get('steamAppID')
                app = app if app and app != '0' else None
                summary = (name + ': скидка ' + str(round(sav)) + '% на игру ' + d.get('title', '') + '. Цена в США была $' + format(normal, '.2f')
                           + ', стала $' + format(sale, '.2f') + ' (в долларах США, для другого региона цена может отличаться). '
                           + ('Оценки Steam: ' + str(pct) + '% положительных из ' + str(n) + ' отзывов. ' if n else '')
                           + ('Metacritic: ' + str(mc) + '. ' if mc else '') + 'Срок окончания скидки в данных не указан.')
                out.append({'id': offer_id(link + '|' + format(sale, '.2f')), 'title': d.get('title', ''), 'summary': summary, 'link': link,
                            'source': 'cheapshark', 'expires_at': None, 'worth': normal, 'kind': 'deal', 'store': name,
                            'steam_app': app, 'steam_pct': pct, 'steam_reviews': n, 'metacritic': mc, 'saved': normal - sale})
            time.sleep(1)
    out.sort(key=lambda x: -x['saved'])
    return out

def fetch_deals():
    import json
    from common import ROOT
    f = ROOT / 'data' / 'deals_cache.json'
    try:
        d = json.loads(f.read_text(encoding='utf-8'))
        if time.time() - d['ts'] < 3 * 3600:
            return d['items']
    except Exception:
        pass
    items = _fetch_deals_raw()
    try:
        from populardeals import fetch_popular
        have = {x['link'] for x in items}
        items += [x for x in fetch_popular() if x['link'] not in have]
    except Exception as e:
        print('популярные скидки недоступны:', e)
    f.write_text(json.dumps({'ts': time.time(), 'items': items}, ensure_ascii=False), encoding='utf-8')
    return items

from chartdeals import chart_deals, chart_live
from epiccharts import epic_chart_deals
from epicdeals import fetch_epic_deals
from epicdeals import fetch_epic_deals

FETCHERS = {'epic-games': fetch_epic, 'gamerpower': fetch_gamerpower, 'steam-chart': chart_deals, 'epic-charts': epic_chart_deals, 'epic-deals': fetch_epic_deals, 'cheapshark': fetch_deals}
LIVE_OVERRIDE = {'steam-chart': lambda: [{'link': l} for l in chart_live()], 'epic-charts': lambda: [{'link': x['link']} for x in fetch_epic_deals()]}

def fetch_all():
    out = []
    for name, fn in FETCHERS.items():
        try:
            out += fn()
        except Exception as ex:
            print('источник', name, 'недоступен:', ex)
    return out

def live_by_source():
    live = {}
    for name, fn in FETCHERS.items():
        try:
            live[name] = {it['link'] for it in (LIVE_OVERRIDE.get(name) or fn)()}
        except Exception as ex:
            print('источник', name, 'недоступен:', ex)
            live[name] = None
    return live

if __name__ == '__main__':
    for it in fetch_all():
        print(it['source'], '|', it['title'][:45], '|', it['expires_at'], '|', it['link'])
