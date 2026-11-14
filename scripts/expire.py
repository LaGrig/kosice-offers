import json, os, time
from common import ROOT, load_offers, offers_lock, update_offers, today
from verify import link_ok

LINKS = ROOT / 'docs' / 'links.json'
REMOVED = ROOT / 'data' / 'removed.jsonl'


def expire_links(t):
    """Physically remove pinned cards whose expires_at date is before today `t`."""
    if not LINKS.exists():
        return
    with offers_lock():
        links = json.loads(LINKS.read_text(encoding='utf-8'))
        keep, dropped = [], []
        for l in links:
            if l.get('expires_at') and l['expires_at'] < t:
                dropped.append(l)
            else:
                keep.append(l)
        if not dropped:
            return
        tmp = LINKS.with_suffix('.tmp')
        tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, LINKS)
    with open(REMOVED, 'a', encoding='utf-8') as f:
        for l in dropped:
            title = (l.get('title') or {}).get('ru') or (l.get('title') or {}).get('uk') or ''
            print('закреп снят:', title)
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'type': 'pin', 'title': title, 'link': l.get('url', ''), 'why': 'истёк срок закрепа'}, ensure_ascii=False) + '\n')


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
    expire_links(t)


if __name__ == '__main__':
    main()
