import html as _html, json, re, requests

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
    meta = {}
    for k, v in re.findall(r'<tr>\s*<td>([^<]{2,30})</td>\s*<td>(.*?)</td>\s*</tr>', html, re.S):
        k = k.strip()
        if k in ('Genre', 'Tags', 'Made with', 'Status', 'Average session'):
            txt = _html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', v))).strip()
            meta[k] = [x.strip() for x in txt.split(',') if x.strip()]
    sig['meta'] = {'genre': meta.get('Genre', []), 'tags': meta.get('Tags', []), 'made_with': meta.get('Made with', []),
                   'status': ' '.join(meta.get('Status', [])), 'session': ' '.join(meta.get('Average session', []))}
    return sig
