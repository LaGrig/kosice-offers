import datetime as dt, re, sys, requests
from common import today, offer_id, load_offers, save_offers
import pipeline

TEXT = {
    'demo': 'Steam: бесплатная демо-версия игры {n} (это демо, а не полная игра). Доступна до {e}. ',
    'playtest': 'Steam: плейтест игры {n}. Нужно запросить доступ на странице игры, участие не гарантировано. Заявки до {e}. ',
    'beta': 'Steam: бета-тест игры {n}. Бесплатный доступ до {e}. ',
}

def main(url, end, kind):
    m = re.search(r'store\.steampowered\.com/app/(\d+)', url)
    if not m:
        print('нужна ссылка вида https://store.steampowered.com/app/ЧИСЛО/...')
        return
    app = m.group(1)
    r = requests.get('https://store.steampowered.com/api/appdetails', params={'appids': app, 'l': 'english', 'cc': 'SK'},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=20).json()[app]
    if not r.get('success'):
        print('Steam не отдал данные об игре')
        return
    d = r['data']
    if kind == 'demo' and not d.get('demos'):
        print('Предупреждение: в данных Steam не указана демо-версия, проверь страницу глазами')
    link = 'https://store.steampowered.com/app/' + app + '/'
    item = {
        'id': offer_id(link), 'title': d['name'], 'link': link, 'source': 'manual-steam',
        'summary': TEXT[kind].format(n=d['name'], e=end) + (d.get('short_description') or '')[:300],
        'expires_at': end, 'worth': None, 'kind': kind,
    }
    offer, why = pipeline.process(item, today().isoformat(), force=True)
    if not offer:
        print('не вышло:', why)
        return
    offers = load_offers()
    if any(o['id'] == offer['id'] for o in offers):
        print('уже есть в списке')
        return
    offer['status'] = 'pending'
    offer['category'] = 'games'
    offer['kind'] = kind
    offers.append(offer)
    save_offers(offers)
    print('добавлено на подтверждение:', d['name'], '|', kind)

kind = sys.argv[3] if len(sys.argv) > 3 else 'demo'
if kind not in TEXT:
    sys.exit('тип: demo, playtest или beta')
end = sys.argv[2] if len(sys.argv) > 2 else (today() + dt.timedelta(days=7)).isoformat()
main(sys.argv[1], end, kind)
