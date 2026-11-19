import datetime as dt, html, json, os, re, requests, time
from common import CFG, ROOT, load_offers, update_offers, today
from blurb import make_blurb
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
HISTORY = ROOT / 'data' / 'digest_history.json'
SRC_RANK = {'epic-games': 0, 'gamerpower': 1}

def esc(s):
    return html.escape(str(s))

def short(d):
    return d[8:10] + '/' + d[5:7] + '/' + d[2:4]

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
        return '⏰ ' + tx['until'] + ' ' + short(e) + ' (' + tx['last'] + ')'
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
    u = urgency(o, tx)
    if d:
        name = clean_game(d['game'])
        state = '💸 ' + tx['deal'] + ' <b>−' + str(d['pct']) + '%</b> · <b>' + esc(d['new']) + '</b> <s>' + esc(d['old']) + '</s> · ' + esc(d['store'])
    elif g:
        name = g['game']
        price = norm_price(g.get('price') or '')
        money = ('<b>' + esc(zero_of(price)) + '</b> <s>' + esc(price) + '</s>') if price else '<b>' + tx['free1'] + '</b>'
        state = '🎁 ' + tx['give'] + ' · ' + money + ' · ' + esc(g['store'])
    else:
        blurb = blurb or hook(o['text'][lang])
    lines = [emoji + ' <b>' + tag + '</b> · ' + name_link(o, name)]
    if state:
        lines.append(state)
    if u:
        lines.append(u)
    if blurb:
        lines.append('💬 <i>' + esc(blurb) + '</i>')
    return '\n'.join(lines)

def block_epic(group, lang, tx):
    if len(group) == 1:
        return block(group[0], lang, tx)
    emoji, tag = tx['tag'].get('games', tx['tag']['other'])
    lines = [emoji + ' <b>' + tag + '</b> · <b>Epic Games Store</b>']
    urgencies = [urgency(o, tx) for o in group]
    same_u = urgencies[0] if len(set(urgencies)) == 1 and urgencies[0] else ''
    lines.append('🎁 ' + tx['give'])
    if same_u:
        lines.append(same_u)
    for o, u in zip(group, urgencies):
        g = o.get('give') or {}
        name = g.get('game') or o['title'][lang]
        price = norm_price(g.get('price') or '')
        money = ('<b>' + esc(zero_of(price)) + '</b> <s>' + esc(price) + '</s>') if price else '<b>' + tx['free1'] + '</b>'
        lines.append('• ' + name_link(o, name) + ' · ' + money)
        if not same_u and u:
            lines.append('  ' + u)
        bl = (o.get('blurb') or {}).get(lang)
        if bl:
            lines.append('  💬 <i>' + esc(bl) + '</i>')
    return '\n'.join(lines)

def ensure_game_blurbs(top, lang):
    """Generate missing game blurbs before rendering the digest."""
    flat = [x for slot in top for x in (slot if isinstance(slot, list) else [slot])]
    fixed = {}
    for o in flat:
        if o.get('category') == 'games' and not (o.get('blurb') or {}).get(lang):
            game = (o.get('deal') or o.get('give') or {}).get('game') or (o.get('title') or {}).get('en', '')
            bl = make_blurb(game, o.get('desc'))
            if bl:
                o['blurb'] = bl
                fixed[o['id']] = bl
    if fixed:
        def apply(cur):
            for o in cur:
                if o['id'] in fixed:
                    o['blurb'] = fixed[o['id']]
        update_offers(apply)

def render_slot(slot, lang, tx):
    return block_epic(slot, lang, tx) if isinstance(slot, list) else block(slot, lang, tx)

def load_sent():
    return set(json.loads(SENT.read_text())) if SENT.exists() else set()

def load_history():
    return json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else {}

def save_history(hist):
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding='utf-8')

def alive_epic_slugs():
    """Return slugs of currently live Epic Games free giveaways, or None if unreachable."""
    try:
        import epic_watch as ew
        out = set()
        for e in ew.fetch():
            w, link = ew.window(e, 'promotionalOffers'), ew.link_of(e)
            tp = ((e.get('price') or {}).get('totalPrice')) or {}
            if w and link and tp.get('originalPrice') and tp.get('discountPrice') == 0:
                s = slug_of(link)
                if s:
                    out.add(s)
        return out
    except Exception as e:
        print('проверка раздач Epic недоступна:', e)
        return None

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

def pick(active, sent, history=None):
    t = today()
    history = history or {}
    day3 = (t - dt.timedelta(days=3)).isoformat()
    size = min(CFG.get('digest_size', 3), 3)

    def left(o):
        e = o.get('expires_at')
        return (dt.date.fromisoformat(e) - t).days if e else 99

    def eligible_rotate(o):
        last = history.get(o['id'])
        return not last or (t - dt.date.fromisoformat(last)).days >= 5

    unsent = [o for o in active if o['id'] not in sent and not o.get('no_digest')]
    city_unsent = sorted(
        [o for o in unsent if o.get('category') != 'games' and not o.get('pinned')],
        key=lambda o: (o.get('expires_at') or '9999', 0 if o.get('category') == 'food' else 1, -o['score']),
    )
    city_rotate = sorted(
        [o for o in active if o.get('category') != 'games' and not o.get('pinned') and not o.get('no_digest') and eligible_rotate(o)],
        key=lambda o: (history.get(o['id'], ''), 0 if o.get('category') == 'food' else 1, -o['score']),
    )
    all_epic = [o for o in active if o['source'] == 'epic-games']
    epic_due = [o for o in all_epic if o['id'] not in sent or left(o) == 1]
    gives = sorted([o for o in unsent if o.get('category') == 'games' and o.get('kind') != 'deal' and o['source'] != 'epic-games' and not o.get('pinned')],
                   key=lambda o: (SRC_RANK.get(o['source'], 2), o.get('expires_at') or '9999', -o['score']))
    deals = sorted([o for o in unsent if o.get('category') == 'games' and o.get('kind') == 'deal' and when(o) >= day3],
                   key=lambda o: (o.get('chart_rank') or 999, -o['score']))

    top = []
    used_ids = set()
    city_first = city_unsent[0] if city_unsent else (city_rotate[0] if city_rotate else None)
    if city_first and len(top) < size:
        top.append(city_first)
        used_ids.add(city_first['id'])
    if epic_due and len(top) < size:
        top.append(all_epic)
        used_ids |= {o['id'] for o in all_epic}
    if gives and len(top) < size:
        top.append(gives[0])
        used_ids.add(gives[0]['id'])

    for o in deals + gives[1:] + city_unsent[1:]:
        if len(top) >= size:
            break
        if o['id'] not in used_ids:
            top.append(o)
            used_ids.add(o['id'])

    # минимум 3: добираем ещё действующими, но уже показанными находками
    if len(top) < size:
        again = sorted([o for o in active if o['id'] not in used_ids and not o.get('pinned') and not o.get('no_digest') and o['source'] != 'manual'],
                       key=lambda o: (0 if o.get('category') != 'games' else (1 if o.get('kind') != 'deal' else 2), o.get('chart_rank') or 999))
        for o in again:
            if len(top) >= size:
                break
            if o['source'] == 'epic-games':
                grp = [x for x in all_epic if x['id'] not in used_ids]
                if grp:
                    top.append(grp)
                    used_ids |= {x['id'] for x in grp}
            else:
                top.append(o)
                used_ids.add(o['id'])
    return top, used_ids

def main():
    t = today().isoformat()
    lang = CFG['digest_lang']
    tx = L[lang]
    preview = bool(os.environ.get('DIGEST_CHAT'))
    active = [o for o in load_offers() if o['status'] == 'active' and (not o.get('expires_at') or o['expires_at'] >= t) and 'example.com' not in (o.get('link') or '')]
    alive_epic = alive_epic_slugs()
    if alive_epic:
        active = [o for o in active if o['source'] != 'epic-games' or slug_of(o['link']) in alive_epic]
    else:
        active = [o for o in active if o['source'] != 'epic-games' or not o.get('expires_at') or o['expires_at'] > t]
    alive = alive_deal_links()
    if alive is not None:
        active = [o for o in active if o.get('kind') != 'deal' or o['source'] not in ('steam-chart', 'epic-charts') or o['link'] in alive]
    top, ids = pick(active, set() if preview else load_sent(), {} if preview else load_history())
    if not top:
        print('нечего публиковать')
        return
    ensure_game_blurbs(top, lang)
    parts = ['🔥 <b>' + tx['head'] + '</b> · ' + short(t) + '\n<i>' + tx['subs'][today().toordinal() % len(tx['subs'])] + '</i>'] + [render_slot(s, lang, tx) for s in top]
    body = {'chat_id': os.environ.get('DIGEST_CHAT') or os.environ['CHANNEL'], 'text': '\n\n'.join(parts), 'parse_mode': 'HTML',
            'disable_web_page_preview': True, 'reply_markup': {'inline_keyboard': [[{'text': tx['open'], 'url': os.environ['MINIAPP_LINK']}]]}}
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:200])
    if r.status_code == 200 and not preview:
        SENT.write_text(json.dumps(sorted(load_sent() | ids)))
        hist = load_history()
        for oid in ids:
            hist[oid] = t
        save_history(hist)
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
