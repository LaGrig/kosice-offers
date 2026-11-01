import json, re, sys, requests
sys.path.insert(0, 'scripts')
from common import ROOT, load_offers
from steam_signal import steam_signal

UA = {'User-Agent': 'Mozilla/5.0'}

def name(t):
    return re.split(r' (бесплатно|вышла|вийшла|безкоштовно)', t)[0].strip()

print('Steam, Green Light:', steam_signal('The Green Light'))
gp = requests.get('https://www.gamerpower.com/api/giveaways', params={'platform': 'pc', 'type': 'game'}, headers=UA, timeout=25).json()
gp = gp if isinstance(gp, list) else []

def users(n):
    for g in gp:
        if n.lower() in g.get('title', '').lower():
            return g.get('users'), g.get('worth'), g.get('end_date')
    return None, None, None

def itch(link):
    try:
        h = requests.get(link, headers=UA, timeout=20).text
    except Exception:
        return {}
    out = {}
    for k, v in re.findall(r'<tr>\s*<td>([^<]{2,30})</td>\s*<td>(.*?)</td>\s*</tr>', h, re.S):
        if k.strip() in ('Genre', 'Tags', 'Status', 'Made with', 'Average session'):
            out[k.strip()] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', v)).strip()[:80]
    return out

rows = []
for l in (ROOT / 'data' / 'rejects.jsonl').read_text(encoding='utf-8').splitlines():
    r = json.loads(l)
    rows.append(('ОТКАЗ ', name(r['title']), r['link']))
for o in load_offers():
    t = o['title'].get('ru', '')
    if o['status'] == 'active' and 'itch' in (t + o['link']).lower():
        rows.append(('ПУБЛИК', name(t), o['link']))
for tag, n, link in rows:
    print(tag, '|', n[:26], '| забрали/цена/до:', users(n), '|', itch(link))
