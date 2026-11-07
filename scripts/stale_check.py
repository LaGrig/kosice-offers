import datetime as dt, json, re, requests, time
from common import CFG, ROOT, load_offers, update_offers, today
from chartdeals import prices, info

LOG = ROOT / 'data' / 'removed.jsonl'
MAX_DAYS = 3
SKIP = ('epic-games', 'gamerpower')
URL = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions'
UA = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}

def epic_slug(url):
    m = re.search(r'/p/([^/?#]+)', url)
    return m.group(1) if m else None

def epic_live():
    cc = {'ua': 'UA', 'sk': 'SK'}.get(CFG.get('deals', {}).get('region', 'ua'), 'UA')
    r = requests.get(URL, params={'locale': 'en-US', 'country': cc, 'allowCountries': cc}, headers=UA, timeout=25)
    r.raise_for_status()
    out = set()
    for e in r.json()['data']['Catalog']['searchStore']['elements']:
        promo = (e.get('promotions') or {}).get('promotionalOffers') or []
        if any((o.get('discountSetting') or {}).get('discountPercentage') == 0 for blk in promo for o in blk.get('promotionalOffers') or []):
            out |= {m['pageSlug'] for m in (e.get('offerMappings') or []) if m.get('pageSlug')}
            out |= {s for s in (e.get('productSlug'), e.get('urlSlug')) if s}
    return out

def main():
    offers = [o for o in load_offers() if o.get('kind') != 'deal' and o['status'] in ('active', 'pending') and o['source'] not in SKIP]
    try:
        live = epic_live()
    except Exception as e:
        live = None
        print('Epic: лента недоступна, ссылки Epic не проверяются:', str(e)[:80])
    gone = {}
    for o in offers:
        link, why = o['link'], None
        age = (today() - dt.date.fromisoformat(o.get('approved_at') or o['found_at'])).days
        if 'store.epicgames.com' in link:
            if live is not None and epic_slug(link) not in live:
                why = 'нет в текущих раздачах Epic'
        elif 'store.steampowered.com/app/' in link:
            try:
                app = int(re.search(r'/app/(\d+)', link).group(1))
                typ = info(app)[1]
                time.sleep(1)
                po = prices([app], 'ua').get(app)
                if typ and typ != 'game':
                    why = 'в Steam это не игра (' + typ + ')'
                elif po and po.get('final', 0) > 0 and po.get('discount_percent', 0) < 100:
                    why = 'в Steam игра платная'
            except Exception as e:
                print('Steam: сбой проверки', link, str(e)[:60])
        elif not o.get('expires_at') and age >= MAX_DAYS:
            why = 'раздача без срока старше ' + str(MAX_DAYS) + ' дней'
        if why:
            gone[o['id']] = (o, why)
            print('снята:', o['title']['ru'][:40], '|', why)
    update_offers(lambda cur: [o for o in cur if o['id'] not in gone])
    with open(LOG, 'a', encoding='utf-8') as f:
        for o, why in gone.values():
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'id': o['id'], 'title': o['title'].get('ru', ''), 'source': o['source'], 'link': o['link'], 'why': why}, ensure_ascii=False) + '\n')
    print('проверено карточек:', len(offers), '| снято:', len(gone))

main()
