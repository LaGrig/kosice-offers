import time, requests
from common import CFG, offer_id

UA = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}

def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

def fetch_popular():
    c = CFG.get('deals', {})
    st = requests.get('https://www.cheapshark.com/api/1.0/stores', headers=UA, timeout=25)
    st.raise_for_status()
    ids = {s['storeName']: s['storeID'] for s in st.json() if s.get('storeName') in ('Steam',)}
    out = []
    for name, sid in ids.items():
        for page in range(c.get('popular_pages', 8)):
            r = requests.get('https://www.cheapshark.com/api/1.0/deals', params={'storeID': sid, 'onSale': 1, 'sortBy': 'Reviews', 'pageSize': 60, 'pageNumber': page}, headers=UA, timeout=25)
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            for d in rows:
                normal, sale, sav = _f(d.get('normalPrice')), _f(d.get('salePrice')), _f(d.get('savings'))
                n = int(_f(d.get('steamRatingCount')))
                if n < c.get('popular_min_reviews', 20000) or normal < c.get('popular_min_normal', 15) or sav < c.get('min_savings', 70):
                    continue
                link = 'https://www.cheapshark.com/redirect?dealID=' + d['dealID']
                pct, mc = int(_f(d.get('steamRatingPercent'))), int(_f(d.get('metacriticScore')))
                app = d.get('steamAppID')
                app = app if app and app != '0' else None
                summary = (name + ': скидка ' + str(round(sav)) + '% на игру ' + d.get('title', '') + '. Цена в США была $' + format(normal, '.2f')
                           + ', стала $' + format(sale, '.2f') + ' (в долларах США, для другого региона цена может отличаться). '
                           + 'Оценки Steam: ' + str(pct) + '% положительных из ' + str(n) + ' отзывов. '
                           + ('Metacritic: ' + str(mc) + '. ' if mc else '') + 'Срок окончания скидки в данных не указан.')
                out.append({'id': offer_id(link + '|' + format(sale, '.2f')), 'title': d.get('title', ''), 'summary': summary, 'link': link,
                            'source': 'cheapshark', 'expires_at': None, 'worth': normal, 'kind': 'deal', 'store': name, 'popular': True,
                            'steam_app': app, 'steam_pct': pct, 'steam_reviews': n, 'metacritic': mc, 'saved': normal - sale})
            time.sleep(1)
    return out
