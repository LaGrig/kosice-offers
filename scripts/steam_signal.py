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
