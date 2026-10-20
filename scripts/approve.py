import sys
from common import load_offers, save_offers

args = sys.argv[1:]
items = load_offers()
pending = [o for o in items if o['status'] == 'pending']
if not args or args[0] == 'list':
    for o in pending:
        print(o['id'], o['score'], o['title'].get('ru', '')[:60], o['link'])
else:
    for o in pending:
        if args[0] == 'all' or o['id'] in args:
            o['status'] = 'active'
    save_offers(items)
