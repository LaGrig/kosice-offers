from common import load_offers, save_offers, today
from verify import link_ok

def main():
    t = today().isoformat()
    keep = []
    for o in load_offers():
        if o['status'] == 'active':
            dead = bool(o.get('expires_at')) and o['expires_at'] < t
            if not dead:
                if link_ok(o['link']):
                    o['fails'] = 0
                else:
                    o['fails'] = o.get('fails', 0) + 1
                    dead = o['fails'] >= 2
            if dead:
                print('снят:', o['id'], o['title'].get('ru', ''))
                continue
        keep.append(o)
    save_offers(keep)

main()
