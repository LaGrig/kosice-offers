from common import load_offers, update_offers, today
from verify import link_ok

def main():
    t = today().isoformat()
    gone, fails = set(), {}
    for o in load_offers():
        if o['status'] != 'active':
            continue
        dead = bool(o.get('expires_at')) and o['expires_at'] < t
        if not dead:
            if link_ok(o['link']):
                fails[o['id']] = 0
            else:
                fails[o['id']] = o.get('fails', 0) + 1
                dead = fails[o['id']] >= 2
        if dead:
            print('снят:', o['id'], o['title'].get('ru', ''))
            gone.add(o['id'])
    def apply(cur):
        out = []
        for o in cur:
            if o['id'] in gone:
                continue
            if o['id'] in fails:
                o['fails'] = fails[o['id']]
            out.append(o)
        return out
    update_offers(apply)

main()
