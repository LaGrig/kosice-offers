import re, requests
from urllib.parse import urlparse

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
BLOCKED_DOMAINS = ('isic.sk', 'zlavomat.sk', 'zlavadna.sk')
ALLOW_403_DOMAINS = ('reddit.com', 'epicgames.com', 'gamerpower.com', 'tesco.sk')

def _host_matches(url, domains):
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith('.' + d) for d in domains)

def link_ok(url):
    if _host_matches(url, BLOCKED_DOMAINS):
        return False
    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers=UA, stream=True)
        if r.status_code in (403, 429) and _host_matches(url, ALLOW_403_DOMAINS):
            return True
        return r.status_code < 400
    except Exception:
        return False

def steam_ok(text):
    urls = re.findall(r'store\.steampowered\.com/(app|sub|bundle)/(\d+)', text)
    for kind, num in urls:
        if kind != 'app':
            return False
        try:
            d = requests.get('https://store.steampowered.com/api/appdetails', params={'appids': num}, timeout=12, headers=UA).json()[num]
            if not d.get('success') or d['data'].get('type') != 'game':
                return False
        except Exception:
            return False
    return True
