import json, re, requests

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}

def _num(x):
    try:
        return float(str(x).replace(',', ''))
    except ValueError:
        return None

def signals(item):
    text = (item.get('title', '') + ' ' + item['link'] + ' ' + item.get('summary', '')[:300]).lower()
    if 'itch' not in text:
        return {}
    sig = {'is_itch': True, 'claimed_users': item.get('users')}
    try:
        r = requests.get(item['link'], headers=UA, timeout=20, allow_redirects=True)
    except Exception as e:
        sig['error'] = str(e)[:80]
        return sig
    sig['page'] = r.url
    if 'itch.io' not in r.url:
        return sig
    html = r.text
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for x in (d if isinstance(d, list) else [d]):
            ar = x.get('aggregateRating') if isinstance(x, dict) else None
            if isinstance(ar, dict):
                sig['rating'] = _num(ar.get('ratingValue'))
                sig['ratings'] = _num(ar.get('ratingCount'))
    if 'ratings' not in sig:
        m = re.search(r'([\d,]+)\s+total ratings', html)
        if m:
            sig['ratings'] = _num(m.group(1))
        m = re.search(r'Rated ([\d.]+) out of 5', html)
        if m:
            sig['rating'] = _num(m.group(1))
    return sig
