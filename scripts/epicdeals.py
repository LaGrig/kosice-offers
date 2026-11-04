import json, time, requests
from common import CFG, ROOT, offer_id

Q = """query searchStoreQuery($allowCountries: String, $category: String, $count: Int, $country: String!, $locale: String, $sortBy: String, $sortDir: String, $start: Int, $onSale: Boolean) {
  Catalog {
    searchStore(allowCountries: $allowCountries, category: $category, count: $count, country: $country, locale: $locale, sortBy: $sortBy, sortDir: $sortDir, start: $start, onSale: $onSale) {
      elements {
        title
        id
        description
        productSlug
        urlSlug
        offerMappings { pageSlug pageType }
        price(country: $country) { totalPrice { discountPrice originalPrice discount currencyCode currencyInfo { decimals } } }
      }
      paging { count total }
    }
  }
}"""
HEAD = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Content-Type': 'application/json'}
CACHE = ROOT / 'data' / 'epic_deals_cache.json'

def _post(start, cc):
    body = {'query': Q, 'variables': {'allowCountries': cc, 'category': 'games/edition/base', 'count': 40, 'country': cc,
                                      'locale': 'en-US', 'sortBy': 'relevancy', 'sortDir': 'DESC', 'start': start, 'onSale': True}}
    r = requests.post('https://store.epicgames.com/graphql', json=body, headers=HEAD, timeout=30)
    r.raise_for_status()
    j = r.json()
    cat = (j.get('data') or {}).get('Catalog')
    if not cat:
        raise RuntimeError('Epic GraphQL: ' + json.dumps(j.get('errors'), ensure_ascii=False)[:300])
    return cat['searchStore']

def _money(v, cur):
    if cur == '₴':
        return format(round(v), ',').replace(',', ' ') + cur
    return ('%.2f' % v).replace('.', ',').replace(',00', '') + cur

def _fetch_raw():
    c = CFG.get('deals', {})
    cc = {'ua': 'UA', 'sk': 'SK'}.get(c.get('region', 'ua'), 'UA')
    out, start = [], 0
    while start < 800:
        st = _post(start, cc)
        els = st.get('elements') or []
        if not els:
            break
        for e in els:
            tp = ((e.get('price') or {}).get('totalPrice')) or {}
            orig, disc = tp.get('originalPrice') or 0, tp.get('discountPrice') or 0
            if orig <= 0 or disc >= orig or disc <= 0:
                continue
            dec = (tp.get('currencyInfo') or {}).get('decimals', 2)
            o, d = orig / 10 ** dec, disc / 10 ** dec
            pct = round(100 * (orig - disc) / orig)
            if pct < c.get('min_savings', 70) or o < c.get('epic_sale_min_local', 500):
                continue
            slug = next((m['pageSlug'] for m in (e.get('offerMappings') or []) if m.get('pageSlug')), None) or e.get('productSlug') or e.get('urlSlug')
            if not slug:
                continue
            link = 'https://store.epicgames.com/p/' + slug.replace('/home', '')
            cur = {'UAH': '₴', 'EUR': '€', 'USD': '$'}.get(tp.get('currencyCode'), tp.get('currencyCode') or '')
            country = {'UA': 'Украине', 'SK': 'Словакии'}.get(cc, 'вашем регионе')
            summary = ('Epic Games Store: скидка ' + str(pct) + '% на игру ' + e.get('title', '') + '. Цена в ' + country + ' была '
                       + _money(o, cur) + ', стала ' + _money(d, cur) + '. Срок окончания скидки в данных не указан.')
            out.append({'id': offer_id(link + '|' + _money(d, cur)), 'title': e.get('title', ''), 'summary': summary, 'link': link,
                        'source': 'epic-deals', 'expires_at': None, 'worth': o, 'kind': 'deal', 'store': 'Epic Games Store', 'popular': True,
                        'steam_app': None, 'steam_pct': 0, 'steam_reviews': 0, 'metacritic': 0, 'saved': o - d, 'epic_id': e.get('id'), 'desc': (e.get('description') or '')[:400],
                        'deal': {'game': e.get('title', ''), 'pct': pct, 'old': _money(o, cur), 'new': _money(d, cur), 'store': 'Epic Games Store'}})
        start += len(els)
        if start >= ((st.get('paging') or {}).get('total') or 10 ** 9):
            break
        time.sleep(1)
    out.sort(key=lambda x: -x['saved'])
    return out

def fetch_epic_deals(ttl=3 * 3600):
    try:
        d = json.loads(CACHE.read_text(encoding='utf-8'))
        if time.time() - d['ts'] < ttl:
            return d['items']
    except Exception:
        pass
    items = _fetch_raw()
    CACHE.write_text(json.dumps({'ts': time.time(), 'items': items}, ensure_ascii=False), encoding='utf-8')
    return items
