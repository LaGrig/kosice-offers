from common import load_offers, save_offers
from api_sources import live_by_source

def main():
    live = live_by_source()
    keep = []
    for o in load_offers():
        links = live.get(o['source'])
        if o['status'] in ('active', 'pending') and links is not None and o['link'] not in links:
            print('раздача закончилась:', o['id'], o['title'].get('ru', ''))
            continue
        keep.append(o)
    save_offers(keep)

main()
