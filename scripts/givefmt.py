import re

def norm_price(s):
    s = (s or '').strip()
    m = re.match(r'^UAH\s*([\d.,]+)$', s)
    if m:
        try:
            return format(round(float(m.group(1).replace(',', ''))), ',').replace(',', ' ') + '₴'
        except ValueError:
            return s
    return s

STORES = {'itch.io': 'itch.io', 'itchio': 'itch.io', 'indiegala': 'IndieGala', 'steam': 'Steam', 'gog': 'GOG',
          'epic games store': 'Epic Games Store', 'stove': 'Stove'}

def give_info(g, plats, worth, note, end):
    title = g.get('title', '')
    game = re.sub(r'\s*\([^)]*\)\s*(key\s+)?giveaway\s*$', '', title, flags=re.I).strip() or title
    m = re.search(r'\(([^)]*)\)', title)
    store = STORES.get(m.group(1).strip().lower()) if m else None
    if not store:
        store = next((n for k, n in (('steam', 'Steam'), ('gog', 'GOG'), ('itch', 'itch.io'), ('epic', 'Epic Games Store'), ('drm', 'DRM-free')) if k in plats.lower()), 'PC')
    return {'game': game, 'store': store, 'price': worth if worth not in ('N/A', '') else '', 'until': end if note.startswith('до') else None}
