import re, requests

UA = {'User-Agent': 'Mozilla/5.0 (kosice-offers-bot)'}

def _n(s):
    return re.sub(r'[™®©:]', '', s).strip().lower()

def clean_title(t):
    t = re.sub(r'\([^)]*\)', ' ', t)
    t = re.sub(r'\b(key\s+)?giveaway\b', ' ', t, flags=re.I)
    return ' '.join(t.split())

def steam_signal(title):
    name = clean_title(title)
    if not name:
        return {}
    try:
        r = requests.get('https://store.steampowered.com/api/storesearch/',
                         params={'term': name, 'l': 'english', 'cc': 'SK'}, headers=UA, timeout=15).json()
        hit = next((i for i in r.get('items', [])
                    if i.get('type') == 'app' and _n(i.get('name', '')) == _n(name)), None)
        if not hit:
            return {}
        s = requests.get('https://store.steampowered.com/appreviews/' + str(hit['id']),
                         params={'json': 1, 'language': 'all', 'purchase_type': 'all'},
                         headers=UA, timeout=15).json().get('query_summary', {})
        pos, neg = s.get('total_positive', 0), s.get('total_negative', 0)
        if pos + neg == 0:
            return {'steam_id': hit['id'], 'steam_reviews': 0}
        return {'steam_id': hit['id'], 'steam_reviews': pos + neg, 'steam_pct': round(100 * pos / (pos + neg))}
    except Exception as e:
        return {'steam_error': str(e)[:80]}

DEFAULT_TIERS = [
    {'min_reviews': 20, 'above_pct': 80},
    {'min_reviews': 50, 'above_pct': 70},
    {'min_reviews': 500, 'above_pct': 50},
]

def steam_strong(sig, tiers=None):
    tiers = tiers or DEFAULT_TIERS
    n = sig.get('steam_reviews', 0)
    pct = sig.get('steam_pct')
    if pct is None:
        return False
    need = None
    for t in sorted(tiers, key=lambda x: x['min_reviews']):
        if n >= t['min_reviews']:
            need = t['above_pct']
    return need is not None and pct > need


def get_json(url, params):
    import time as _t
    last = None
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=15)
            if r.status_code == 200:
                return r.json()
            last = 'HTTP ' + str(r.status_code)
        except Exception as e:
            last = str(e)[:60]
        _t.sleep(2 * (i + 1))
    raise RuntimeError(last)
