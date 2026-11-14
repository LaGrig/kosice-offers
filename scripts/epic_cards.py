import datetime as dt, re, sys
sys.path.insert(0, 'scripts')
from common import load_offers, update_offers, offer_id, today
from blurb import make_blurb
import epic_watch as ew
from epicdeals import _money

T = {'uk': 'Безкоштовно в Epic Games Store до {d}. Зазвичай {p}.', 'ru': 'Бесплатно в Epic Games Store до {d}. Обычно {p}.',
     'en': 'Free on Epic Games Store until {d}. Usually {p}.', 'sk': 'Zadarmo v Epic Games Store do {d}. Zvyčajne {p}.'}

def slug(link):
    m = re.search(r'/p/([^/?#]+)', link or '')
    return m.group(1) if m else None

def main():
    st = ew.state()
    cards = []
    for e in ew.fetch():
        w, link = ew.window(e, 'promotionalOffers'), ew.link_of(e)
        tp = ((e.get('price') or {}).get('totalPrice')) or {}
        if not (w and link and tp.get('originalPrice') and tp.get('discountPrice') == 0):
            continue
        dec = (tp.get('currencyInfo') or {}).get('decimals', 2)
        sym = ew.CUR.get(tp.get('currencyCode'), tp.get('currencyCode') or '')
        orig = _money(tp['originalPrice'] / 10 ** dec, sym)
        name, end = e.get('title', ''), w[1].astimezone(dt.timezone.utc).date().isoformat()
        ds = end[8:10] + '/' + end[5:7] + '/' + end[:4]
        cid = offer_id(link)
        desc = (e.get('description') or '')[:400]
        card = {'id': cid, 'title': {l: name for l in T}, 'text': {l: T[l].format(d=ds, p=orig) for l in T}, 'category': 'games', 'link': link,
                'source': 'epic-games', 'found_at': today().isoformat(), 'approved_at': today().isoformat(), 'expires_at': end, 'score': 95,
                'worth': tp['originalPrice'] / 10 ** dec, 'status': 'active', 'announced': False, 'desc': desc,
                'give': {'game': name, 'store': 'Epic Games Store', 'price': orig, 'until': end}}
        cards.append(card)
    have_now = {slug(o['link']) for o in load_offers() if o['source'] == 'epic-games'}
    for c in cards:
        if slug(c['link']) not in have_now:
            bl = make_blurb(c['give']['game'], c.get('desc'))
            if bl:
                c['blurb'] = bl

    def apply(cur):
        have = {slug(o['link']) for o in cur if o['source'] == 'epic-games'}
        fresh = [c for c in cards if slug(c['link']) not in have]
        for c in fresh:
            print('новая карточка раздачи:', c['give']['game'])
        dup = {slug(c['link']) for c in cards}
        out = [o for o in cur if not (o['source'].startswith('reddit') and slug(o['link']) in dup)]
        return out + fresh
    update_offers(apply)
    print('карточки текущих раздач Epic:', [c['give']['game'] + (' (анонс уже был)' if c['announced'] else '') for c in cards])

if __name__ == '__main__':
    main()
