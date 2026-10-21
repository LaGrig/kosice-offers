import json
from common import ROOT, today

F = ROOT / 'data' / 'auto_rejects.jsonl'

def known():
    if not F.exists():
        return set()
    return {json.loads(l)['id'] for l in F.read_text(encoding='utf-8').splitlines() if l.strip()}

def log_auto_reject(item, why):
    if item['id'] in known():
        return
    rec = {'date': today().isoformat(), 'id': item['id'], 'title': item['title'], 'link': item['link'],
           'source': item['source'], 'why': why, 'item': item, 'reported': False}
    with open(F, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
