import datetime as dt, html, json, os, re, requests, time
from common import CFG, ROOT, load_offers, today
from givefmt import norm_price
from dealtext import clean_game

L = {
    'uk': {'head': 'Знахідки дня', 'subs': ['Забирай, поки діє 👇', 'Що забрати сьогодні 👇', 'Коротко і по ділу 👇'], 'deal': 'Знижка', 'give': 'Роздача', 'free1': 'Безкоштовно',
           'last': 'останній день', 'days': 'ще {n} дн.', 'until': 'до', 'top': 'топ', 'open': '📲 Відкрити застосунок',
           'tag': {'games': ('🎮', 'Гра'), 'food': ('🍔', 'Їжа'), 'events': ('🎟', 'Подія'), 'places': ('📍', 'Місце'), 'jobs': ('💼', 'Підробіток'), 'it_soft': ('💻', 'Софт'), 'services': ('🧾', 'Сервіс'), 'study': ('🎓', 'Навчання'), 'other': ('✨', 'Знахідка')}},
    'ru': {'head': 'Находки дня', 'subs': ['Забирай, пока действует 👇', 'Что забрать сегодня 👇', 'Коротко и по делу 👇'], 'deal': 'Скидка', 'give': 'Раздача', 'free1': 'Бесплатно',
           'last': 'последний день', 'days': 'ещё {n} дн.', 'until': 'до', 'top': 'топ', 'open': '📲 Открыть приложение',
           'tag': {'games': ('🎮', 'Игра'), 'food': ('🍔', 'Еда'), 'events': ('🎟', 'Событие'), 'places': ('📍', 'Место'), 'jobs': ('💼', 'Подработка'), 'it_soft': ('💻', 'Софт'), 'services': ('🧾', 'Сервис'), 'study': ('🎓', 'Учёба'), 'other': ('✨', 'Находка')}},
    'en': {'head': 'Finds of the day', 'subs': ['Grab them while they last 👇', 'What to grab today 👇', 'Short and to the point 👇'], 'deal': 'Deal', 'give': 'Giveaway', 'free1': 'Free',
           'last': 'last day', 'days': '{n} d left', 'until': 'until', 'top': 'top', 'open': '📲 Open the app',
           'tag': {'games': ('🎮', 'Game'), 'food': ('🍔', 'Food'), 'events': ('🎟', 'Event'), 'places': ('📍', 'Place'), 'jobs': ('💼', 'Job'), 'it_soft': ('💻', 'Software'), 'services': ('🧾', 'Service'), 'study': ('🎓', 'Study'), 'other': ('✨', 'Find')}},
    'sk': {'head': 'Objavy dňa', 'subs': ['Chyť ich, kým platia 👇', 'Čo si dnes vziať 👇', 'Stručne a k veci 👇'], 'deal': 'Zľava', 'give': 'Rozdávanie', 'free1': 'Zadarmo',
           'last': 'posledný deň', 'days': 'ešte {n} d.', 'until': 'do', 'top': 'top', 'open': '📲 Otvoriť aplikáciu',
           'tag': {'games': ('🎮', 'Hra'), 'food': ('🍔', 'Jedlo'), 'events': ('🎟', 'Udalosť'), 'places': ('📍', 'Miesto'), 'jobs': ('💼', 'Brigáda'), 'it_soft': ('💻', 'Softvér'), 'services': ('🧾', 'Služba'), 'study': ('🎓', 'Štúdium'), 'other': ('✨', 'Objav')}},
}
SENT = ROOT / 'data' / 'digest_sent.json'
SRC_RANK = {'epic-games': 0, 'gamerpower': 1}

def esc(s):
    return html.escape(str(s))

def short(d):
    return d[8:10] + '/' + d[5:7] + '/' + d[:4]

def when(o):
    return o.get('approved_at') or o['found_at']

def hook(text):
    text = ' '.join(text.split())
    if len(text) <= 160:
        return text
    cut = text.find('. ')
    return (text if cut == -1 else text[:cut + 1])[:160]

def name_link(o, name):
    return '<a href="' + html.escape(o['link'], quote=True) + '"><b>' + esc(name) + '</b></a>'

def urgency(o, tx):
    e = o.get('expires_at')
    if not e:
        return ''
    left = (dt.date.fromisoformat(e) - today()).days
    if left <= 0:
        return '⏰ ' + tx['last']
    if left <= 3:
        return '⏰ ' + tx['days'].format(n=left)
    return '⏳ ' + tx['until'] + ' ' + short(e)

def zero_of(price):
    if price.endswith('₴'):
        return '0₴'
    if price.startswith('$'):
        return '$0'
    if price.endswith('€'):
        return '0€'
    return '0'

def block(o, lang, tx):
    d, g = o.get('deal'), o.get('give')
    emoji, tag = tx['tag'].get(o['category'], tx['tag']['other'])
    state, name, blurb = '', o['title'][lang], (o.get('blurb') or {}).get(lang)
    if d:
        name = clean_game(d['game'])
        rank = d.get('rank_sales') or d.get('rank_play')
        state = '💸 ' + tx['deal'] + ' <b>−' + str(d['pct']) + '%</b> · <b>' + esc(d['new']) + '</b> <s>' + esc(d['old']) + '</s> · ' + esc(d['store'])
        if rank:
            state += ' · 🏆 ' + tx['top'] + '-' + str(rank)
    elif g:
        name = g['game']
        price = norm_price(g.get('price') or '')
        money = ('<b>' + esc(zero_of(price)) + '</b> <s>' + esc(price) + '</s>') if price else '<b>' + tx['free1'] + '</b>'
        state = '🎁 ' + tx['give'] + ' · ' + money + ' · ' + esc(g['store'])
        u = urgency(o, tx)
        if u:
            state += ' · ' + u
    else:
        blurb = blurb or hook(o['text'][lang])
        state = urgency(o, tx)
    lines = [emoji + ' <b>' + tag + '</b> · ' + name_link(o, name)]
    if state:
        lines.append(state)
    if blurb:
        lines.append('💬 <i>' + esc(blurb) + '</i>')
    return '\n'.join(lines)

def load_sent():
    return set(json.loads(SENT.read_text())) if SENT.exists() else set()

def alive_deal_links():
    try:
        from chartdeals import chart_live
        from epicdeals import fetch_epic_deals
        live = set(chart_live())
        if any(o['source'] == 'epic-charts' for o in load_offers()):
            live |= {x['link'] for x in fetch_epic_deals(ttl=0)}
        return live
    except Exception as e:
        print('проверка цен недоступна:', e)
        return None

def slug_of(link):
    m = re.search(r'/p/([^/?#]+)', link or '')
    return m.group(1) if m else None

def pick(active, sent):
    ann = {slug_of(o['link']) for o in active if o.get('announced') and slug_of(o['link'])}
    active = [o for o in active if not (slug_of(o['link']) in ann and not o.get('announced'))]
    day3 = (today() - dt.timedelta(days=3)).isoformat()
    day7 = (today() - dt.timedelta(days=7)).isoformat()
    new = [o for o in active if o['id'] not in sent]
    gives = sorted([o for o in new if o.get('kind') != 'deal' and when(o) >= day7 and not (o.get('announced') and (o.get('expires_at') or '9999') > today().isoformat())],
                   key=lambda o: (SRC_RANK.get(o['source'], 2), o.get('expires_at') or '9999', -o['score']))
    deals = sorted([o for o in new if o.get('kind') == 'deal' and when(o) >= day3],
                   key=lambda o: (o.get('chart_rank') or 999, -o['score']))
    top = gives[:1] + deals[:2]
    for o in gives[1:] + deals[2:]:
        if len(top) >= CFG['digest_size']:
            break
        top.append(o)
    return top

def main():
    t = today().isoformat()
    lang = CFG['digest_lang']
    tx = L[lang]
    preview = bool(os.environ.get('DIGEST_CHAT'))
    active = [o for o in load_offers() if o['status'] == 'active' and (not o.get('expires_at') or o['expires_at'] >= t)]
    alive = alive_deal_links()
    if alive is not None:
        active = [o for o in active if o.get('kind') != 'deal' or o['source'] not in ('steam-chart', 'epic-charts') or o['link'] in alive]
    top = pick(active, set() if preview else load_sent())
    if not top:
        print('нечего публиковать')
        return
    ids = {o['id'] for o in top}
    parts = ['🔥 <b>' + tx['head'] + '</b> · ' + short(t) + '\n<i>' + tx['subs'][today().toordinal() % len(tx['subs'])] + '</i>'] + [block(o, lang, tx) for o in top]
    body = {'chat_id': os.environ.get('DIGEST_CHAT') or os.environ['CHANNEL'], 'text': '\n\n'.join(parts), 'parse_mode': 'HTML',
            'disable_web_page_preview': True, 'reply_markup': {'inline_keyboard': [[{'text': tx['open'], 'url': os.environ['MINIAPP_LINK']}]]}}
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:200])
    if r.status_code == 200 and not preview:
        SENT.write_text(json.dumps(sorted(load_sent() | ids)))
        try:
            mid = r.json()['result']['message_id']
            f = ROOT / 'data' / 'channel_posts.json'
            posts = json.loads(f.read_text(encoding='utf-8')) if f.exists() else []
            posts.append({'ts': time.strftime('%F %T'), 'message_id': mid, 'label': 'дайджест'})
            f.write_text(json.dumps(posts[-200:], ensure_ascii=False), encoding='utf-8')
            requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', timeout=30, json={'chat_id': os.environ['OWNER_ID'],
                          'text': '✅ Дайджест опубліковано в каналі', 'reply_markup': {'inline_keyboard': [[{'text': '🗑 Видалити з каналу', 'callback_data': 'dm:' + str(mid)}]]}})
        except Exception as e:
            print('не удалось записать пост:', e)

if __name__ == '__main__':
    main()
