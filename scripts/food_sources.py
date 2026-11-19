import datetime as dt
import html
import json
import re
import requests
from common import offer_id, today

HEAD = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
}

LIDL_API = 'https://www.lidl.sk/q/api/search'
LIDL_MON = 'https://www.lidl.sk/c/store/ponuka-od-pondelka/a10102636'
LIDL_SKIP_CAT = re.compile(r'(?i)(zvierat|krmivo|drogeria|hygiena|detská|hračky|víno|pivo|liehoviny|prosecco|šampanské)')
LIDL_SKIP_TITLE = re.compile(r'(?i)(plienky|pre psov|pre mačky|drevená kuchynka|prosecco|víno|pivo)')

KOSICE_DELIVERY_SITES = [
    {'name': 'pizzaBurger Originál Košice', 'url': 'https://www.pizzaburgerkosice.sk/', 'combo_anchor': '#menu-combo', 'promo_url': 'https://www.pizzaburgerkosice.sk/promocje'},
    {'name': 'Barcianka (Pizza Barca)', 'url': 'https://www.barcianka.sk/', 'promo_url': 'https://www.barcianka.sk/promocje'},
    {'name': 'Bistro Ferum Jet', 'url': 'https://www.bistroferumjet.sk/', 'promo_url': 'https://www.bistroferumjet.sk/promocje'},
    {'name': 'Pivovar U medveďa Košice', 'url': 'https://www.umedveda.sk/', 'promo_url': 'https://www.umedveda.sk/promocje'},
    {'name': 'Pizza z pece Košice', 'url': 'https://www.pizzazpece.sk/'},
    {'name': 'Andiamo Group Košice', 'url': 'https://www.andiamogroup.eu/kalendar-akcii-aktualne'},
]


def _parse_badge_dates(badges):
    """Extract badge text and end ISO date from Lidl availability badges."""
    t = today()
    for b in (badges or []):
        txt = (b.get('text') or '').strip()
        m = re.findall(r'(\d{1,2})\.(\d{1,2})\.', txt)
        if m:
            d, mo = int(m[-1][0]), int(m[-1][1])
            try:
                cand = dt.date(t.year, mo, d)
            except ValueError:
                continue
            if (t - cand).days > 30:
                cand = dt.date(t.year + 1, mo, d)
            return txt, cand.isoformat()
        if txt:
            return txt, None
    return '', None


def _lidl_extract_item(gd):
    """Parse one Lidl gridbox data dict into a normalized deal record or None."""
    title = ' '.join((gd.get('fullTitle') or gd.get('title') or '').lstrip('- ').split())
    canon = gd.get('canonicalUrl') or ''
    cat = (gd.get('keyfacts') or {}).get('wonCategoryPrimary') or ''
    if not title or not canon or LIDL_SKIP_CAT.search(cat) or LIDL_SKIP_TITLE.search(title):
        return None
    p = gd.get('price') or {}
    lp = (gd.get('lidlPlus') or [{}])[0].get('price') or {}
    old_p = p.get('oldPrice') or lp.get('oldPrice')
    new_p = p.get('price')
    lp_p = lp.get('price')
    best_p = lp_p if (lp_p and (not new_p or lp_p < new_p)) else new_p
    if not old_p or not best_p or best_p >= old_p:
        return None
    pct = round(100 * (old_p - best_p) / old_p)
    badges = ((gd.get('stockAvailability') or {}).get('badgeInfo') or {}).get('badges') or []
    badge_txt, exp = _parse_badge_dates(badges)
    if exp and exp < today().isoformat():
        return None
    pack = (p.get('packaging') or lp.get('packaging') or {}).get('text') or ''
    link = 'https://www.lidl.sk' + canon
    old_s = f"{old_p:.2f}".replace('.', ',') + ' €'
    new_s = f"{best_p:.2f}".replace('.', ',') + ' €'
    lp_note = ' (с картой Lidl Plus)' if (lp_p and best_p == lp_p) else ''
    pack_note = f' ({pack})' if pack else ''
    when_note = f' Период акции: {badge_txt}.' if badge_txt else ''
    summary = (
        f"Lidl.sk: скидка {pct}% на продукт «{title}»{pack_note}. "
        f"Цена была {old_s}, стала {new_s}{lp_note}.{when_note} Категория Lidl: {cat}."
    )
    return {
        'id': offer_id(link + '|' + new_s),
        'title': f"Lidl: {title} −{pct}% ({new_s} вместо {old_s})",
        'summary': summary,
        'link': link,
        'source': 'lidl-food',
        'expires_at': exp,
        'worth': float(old_p),
        'pct': pct,
        'new_price': new_s,
        'old_price': old_s,
        'packaging': pack,
        'lidl_plus': bool(lp_p and best_p == lp_p),
        'badge': badge_txt,
        'raw_title': title,
    }


def fetch_lidl_food(min_discount=30, max_items=6):
    """Fetch top discounted student-relevant grocery items directly from Lidl.sk."""
    raw_items = {}
    try:
        r = requests.get(
            LIDL_API,
            params={'assortment': 'SK', 'locale': 'sk_SK', 'version': 'v2.0.0', 'sort': 'percentageDiscount-desc', 'category.id': '10068374'},
            headers=HEAD,
            timeout=15,
        )
        if r.status_code == 200:
            for it in (r.json().get('items') or []):
                gd = (it.get('gridbox') or {}).get('data') or {}
                if gd.get('canonicalUrl'):
                    raw_items[gd['canonicalUrl']] = gd
    except Exception as e:
        print('Lidl API warning:', e)
    try:
        r2 = requests.get(LIDL_MON, headers=HEAD, timeout=15)
        if r2.status_code == 200:
            for raw in re.findall(r'data-grid-data="([^"]+)"', r2.text):
                gd = json.loads(html.unescape(raw))
                if isinstance(gd, dict) and gd.get('canonicalUrl'):
                    raw_items.setdefault(gd['canonicalUrl'], gd)
    except Exception as e:
        print('Lidl Mon warning:', e)

    out = []
    for gd in raw_items.values():
        rec = _lidl_extract_item(gd)
        if rec and rec['pct'] >= min_discount:
            out.append(rec)
    out.sort(key=lambda x: (-x['pct'], x.get('expires_at') or '9999'))
    return out[:max_items]


def _walk_menuitems(obj, acc):
    if isinstance(obj, dict):
        if obj.get('@type') == 'MenuItem':
            acc.append(obj)
        for v in obj.values():
            _walk_menuitems(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            _walk_menuitems(x, acc)


def _scan_combo_discounts(site, html_text):
    """Find MenuItem JSON-LD entries with strikethrough old price vs lower current price."""
    items = []
    for blk in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, re.S):
        try:
            _walk_menuitems(json.loads(blk), items)
        except Exception:
            continue
    seen = set()
    combos = []
    for it in items:
        raw_name = it.get('name') or ''
        clean_name = ' '.join(raw_name.replace('\u0336', '').split())
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*€', clean_name)
        new_p = (it.get('offers') or {}).get('price')
        if not (m and new_p):
            continue
        old_p = float(m.group(1).replace(',', '.'))
        new_p = float(new_p)
        if old_p <= new_p:
            continue
        pct = round(100 * (old_p - new_p) / old_p)
        if pct < 15:
            continue
        title = re.sub(r'\s*[–-]?\s*\d+(?:[.,]\d+)?\s*€.*$', '', clean_name).strip()
        if title in seen:
            continue
        seen.add(title)
        desc = ' '.join((it.get('description') or '').split())
        combos.append({
            'title': title,
            'old': old_p,
            'new': new_p,
            'pct': pct,
            'desc': desc,
        })
    combos.sort(key=lambda x: -x['pct'])
    if not combos:
        return None
    link = site['url'].rstrip('/') + '/' + site.get('combo_anchor', '').lstrip('/')
    best = combos[0]
    parts = [
        f"{c['title']}: {c['new']:.2f} € вместо {c['old']:.2f} € (−{c['pct']}%) — {c['desc']}"
        for c in combos[:3]
    ]
    summary = f"{site['name']} (Кошице): выгодные комбо-наборы на компанию со скидками до {best['pct']}%. " + '; '.join(parts)
    return {
        'id': offer_id(link),
        'title': f"{site['name']}: комбо-сеты со скидкой до −{best['pct']}%",
        'summary': summary[:1200],
        'link': link,
        'source': 'kosice-delivery',
        'expires_at': None,
        'worth': best['old'],
        'combos': combos,
    }


def _scan_promocje(site, promo_url):
    """Extract major free-item or >=15% promotions from Restaumatic /promocje pages."""
    r = requests.get(promo_url, headers=HEAD, timeout=12)
    if r.status_code != 200:
        return None
    clean = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', r.text, flags=re.S | re.I)
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', clean)).strip()
    if 'Momentálne nie sú žiadne akcie' in txt:
        return None
    m = re.search(r'Pozri si naše Najlepšie propagácie\s+(.*?)\s+Akcia platí v:', txt)
    if not m:
        return None
    promo_txt = m.group(1).strip()
    if not re.search(r'(?i)(zadarmo|grátis|2\+1|1\+1|(?:[2-9]\d|1[5-9])\s*%)', promo_txt):
        return None
    return {
        'id': offer_id(promo_url),
        'title': f"{site['name']}: акция «{promo_txt[:60]}»",
        'summary': f"{site['name']} (Кошице): акция на официальном сайте — {promo_txt}",
        'link': promo_url,
        'source': 'kosice-delivery',
        'expires_at': None,
        'worth': 10.0,
        'promo_text': promo_txt,
    }


def fetch_kosice_delivery():
    """Scan direct official Košice restaurant/delivery sites, emitting at most one card per venue."""
    out = []
    for site in KOSICE_DELIVERY_SITES:
        combo, pr = None, None
        try:
            r = requests.get(site['url'], headers=HEAD, timeout=12)
            if r.status_code == 200:
                combo = _scan_combo_discounts(site, r.text)
        except Exception as e:
            print('Kosice site warning:', site['url'], str(e)[:60])
        if site.get('promo_url'):
            try:
                pr = _scan_promocje(site, site['promo_url'])
            except Exception as e:
                print('Kosice promo warning:', site['promo_url'], str(e)[:60])
        if combo and pr:
            combo['title'] = f"{site['name']}: комбо до −{combo['combos'][0]['pct']}% и подарок"
            combo['summary'] = (combo['summary'] + ' Плюс акция на сайте: ' + pr['promo_text'])[:1400]
            out.append(combo)
        elif combo:
            out.append(combo)
        elif pr:
            out.append(pr)
    return out


if __name__ == '__main__':
    print('=== LIDL FOOD (>=30%) ===')
    for x in fetch_lidl_food():
        print(x['pct'], '% |', x['raw_title'], '|', x['old_price'], '->', x['new_price'], '| exp:', x['expires_at'], '|', x['link'])
    print('=== KOSICE DELIVERY ===')
    for x in fetch_kosice_delivery():
        print(x['source'], '|', x['title'], '|', x['link'])
        print('  ', x['summary'][:200])
