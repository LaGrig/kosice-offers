import datetime as dt, html, json, os, requests
from common import CFG, ROOT, load_offers, today
from givefmt import norm_price
from dealtext import clean_game

L = {
    'uk': {'head': 'Знахідки дня', 'subs': ['Забирай, поки діє 👇', 'Що забрати сьогодні 👇', 'Коротко і по ділу 👇'], 'free': 'БЕЗКОШТОВНО', 'deals': 'ЗНИЖКИ', 'other': 'ЩЕ',
           'free1': 'Безкоштовно', 'last': 'останній день', 'days': 'ще {n} дн.', 'until': 'до', 'top': 'топ', 'open': '📲 Відкрити застосунок'},
    'ru': {'head': 'Находки дня', 'subs': ['Забирай, пока действует 👇', 'Что забрать сегодня 👇', 'Коротко и по делу 👇'], 'free': 'БЕСПЛАТНО', 'deals': 'СКИДКИ', 'other': 'ЕЩЁ',
           'free1': 'Бесплатно', 'last': 'последний день', 'days': 'ещё {n} дн.', 'until': 'до', 'top': 'топ', 'open': '📲 Открыть приложение'},
    'en': {'head': 'Finds of the day', 'subs': ['Grab them while they last 👇', 'What to grab today 👇', 'Short and to the point 👇'], 'free': 'FREE', 'deals': 'DEALS', 'other': 'MORE',
           'free1': 'Free', 'last': 'last day', 'days': '{n} d left', 'until': 'until', 'top': 'top', 'open': '📲 Open the app'},
    'sk': {'head': 'Objavy dňa', 'subs': ['Chyť ich, kým platia 👇', 'Čo si dnes vziať 👇', 'Stručne a k veci 👇'], 'free': 'ZADARMO', 'deals': 'ZĽAVY', 'other': 'ĎALEJ',
           'free1': 'Zadarmo', 'last': 'posledný deň', 'days': 'ešte {n} d.', 'until': 'do', 'top': 'top', 'open': '📲 Otvoriť aplikáciu'},
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
    if d:
        rank = d.get('rank_sales') or d.get('rank_play')
        tail = esc(d['store']) + (' · 🏆 ' + tx['top'] + '-' + str(rank) if rank else '')
        return ('💸 ' + name_link(o, clean_game(d['game'])) + ' · <b>−' + str(d['pct']) + '%</b>\n<s>' + esc(d['old']) + '</s> → <b>' + esc(d['new']) + '</b> · ' + tail)
    if g:
        price = norm_price(g.get('price') or '')
        line = ('<s>' + esc(price) + '</s> → <b>' + esc(zero_of(price)) + '</b>') if price else '<b>' + tx['free1'] + '</b>'
        u = urgency(o, tx)
        return '🎁 ' + name_link(o, g['game']) + ' · ' + esc(g['store']) + '\n' + line + (' · ' + u if u else '')
    u = urgency(o, tx)
    return '✨ ' + name_link(o, o['title'][lang]) + '\n' + esc(hook(o['text'][lang])) + (' · ' + u if u else '')

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

def pick(active, sent):
    day3 = (today() - dt.timedelta(days=3)).isoformat()
    day7 = (today() - dt.timedelta(days=7)).isoformat()
    new = [o for o in active if o['id'] not in sent]
    gives = sorted([o for o in new if o.get('kind') != 'deal' and when(o) >= day7],
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
    active = [o for o in load_offers() if o['status'] == 'active' and (not o.get('expires_at') or o['expires_at'] >= t)]
    alive = alive_deal_links()
    if alive is not None:
        active = [o for o in active if o.get('kind') != 'deal' or o['source'] not in ('steam-chart', 'epic-charts') or o['link'] in alive]
    top = pick(active, load_sent())
    if not top:
        print('нечего публиковать')
        return
    ids = {o['id'] for o in top}
    sections = [('🎁', tx['free'], [o for o in top if o.get('give')]),
                ('💸', tx['deals'], [o for o in top if o.get('deal')]),
                ('✨', tx['other'], [o for o in top if not o.get('give') and not o.get('deal')])]
    parts = ['🔥 <b>' + tx['head'] + '</b> · ' + short(t) + '\n<i>' + tx['subs'][today().toordinal() % len(tx['subs'])] + '</i>']
    for emoji, title, items in sections:
        if items:
            parts.append(emoji + ' <b>' + title + '</b>\n' + '\n\n'.join(block(o, lang, tx) for o in items))
    preview = bool(os.environ.get('DIGEST_CHAT'))
    body = {'chat_id': os.environ.get('DIGEST_CHAT') or os.environ['CHANNEL'], 'text': '\n\n'.join(parts), 'parse_mode': 'HTML',
            'disable_web_page_preview': True, 'reply_markup': {'inline_keyboard': [[{'text': tx['open'], 'url': os.environ['MINIAPP_LINK']}]]}}
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:200])
    if r.status_code == 200 and not preview:
        SENT.write_text(json.dumps(sorted(load_sent() | ids)))

main()
