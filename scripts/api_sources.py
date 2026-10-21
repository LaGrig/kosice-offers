import re, datetime as dt, requests
from common import offer_id, CFG

UA = {'User-Agent': 'Mozilla/5.0 (kosice-offers-bot)'}
EPIC_COUNTRY = 'SK'

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
        if ow < CFG.get('min_worth', {}).get('epic', 10):
            continue
        orig = (price.get('fmtPrice') or {}).get('originalPrice', '')
        summary = ('Epic Games Store: бесплатная раздача игры ' + e.get('title', '') + '. Обычная цена ' + orig
                   + '. Бесплатно до ' + end + ' (UTC). ' + (e.get('description') or '')[:300])
        out.append({'id': offer_id(link), 'title': e.get('title', ''), 'summary': summary,
                    'link': link, 'source': 'epic-games', 'expires_at': end, 'worth': ow})
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
            continue
        summary = (plats + ': бесплатная раздача ' + g.get('title', '') + ' (обычная цена ' + worth + '). Бесплатно '
                   + note + '. ' + (g.get('description') or '')[:300] + ' ' + (g.get('instructions') or '')[:300])
        out.append({'id': offer_id(link), 'title': g.get('title', ''), 'summary': summary,
                    'link': link, 'source': 'gamerpower', 'expires_at': end, 'worth': wv})
    return out

FETCHERS = {'epic-games': fetch_epic, 'gamerpower': fetch_gamerpower}

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
            live[name] = {it['link'] for it in fn()}
        except Exception as ex:
            print('источник', name, 'недоступен:', ex)
            live[name] = None
    return live

if __name__ == '__main__':
    for it in fetch_all():
        print(it['source'], '|', it['title'][:45], '|', it['expires_at'], '|', it['link'])
