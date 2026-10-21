import re, requests

UA = {'User-Agent': 'Mozilla/5.0 (kosice-offers-bot)'}

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
                    if i.get('type') == 'app' and i.get('name', '').strip().lower() == name.lower()), None)
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
