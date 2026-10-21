import json, sys
from common import load_offers, save_offers, today
from autolog import F
import pipeline

def main(oid):
    rows = [json.loads(l) for l in F.read_text(encoding='utf-8').splitlines() if l.strip()]
    rec = next((r for r in rows if r['id'] == oid), None)
    if not rec:
        print('не найдено в журнале')
        return
    offer, why = pipeline.process(rec['item'], today().isoformat(), force=True)
    if not offer:
        print('не вышло:', why)
        return
    offers = load_offers()
    if any(o['id'] == offer['id'] for o in offers):
        print('уже есть в списке')
        return
    offer['status'] = 'pending'
    offers.append(offer)
    save_offers(offers)
    print('RESCUED')

main(sys.argv[1])
