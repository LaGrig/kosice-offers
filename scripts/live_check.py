from common import load_offers, update_offers
from api_sources import live_by_source

def main():
    live = live_by_source()
    gone = set()
    for o in load_offers():
        links = live.get(o['source'])
        if o['status'] in ('active', 'pending') and links is not None and o['link'] not in links:
            print('раздача закончилась:', o['id'], o['title'].get('ru', ''))
            gone.add(o['id'])
    update_offers(lambda cur: [o for o in cur if o['id'] not in gone])

main()
