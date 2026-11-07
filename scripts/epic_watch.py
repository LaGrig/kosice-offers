import datetime as dt, html, json, os, sys, time, requests
from zoneinfo import ZoneInfo
from common import CFG, ROOT, update_offers, offer_id, today
from blurb import make_blurb
from epicdeals import _money
import digest as dg

URL = 'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions'
UA = {'User-Agent': 'kosice-offers-bot (+https://github.com/LaGrig/kosice-offers)'}
TZ = ZoneInfo('Europe/Bratislava')
STATE = ROOT / 'data' / 'epic_watch.json'
POSTS = ROOT / 'data' / 'channel_posts.json'
DRY = '--dry' in sys.argv
CUR = {'UAH': '₴', 'EUR': '€', 'USD': '$'}

TXT = {
    'uk': {'now': 'Epic Games Store · безкоштовно зараз', 'soon': 'Epic Games Store · скоро безкоштовно', 'myst': 'Epic Games Store · гра-сюрприз', 'game': 'Гра', 'until': 'до',
           'today': 'сьогодні', 'tomorrow': 'завтра', 'soon_body': '{day} о {time} Epic роздає: {names}. Не пропусти 👇',
           'myst_body': '{day} о {time} зʼявиться безкоштовна гра, назву Epic поки ховає. Роздача триває близько {h} год, не пропусти 👇', 'open': '📲 Відкрити застосунок'},
    'ru': {'now': 'Epic Games Store · бесплатно сейчас', 'soon': 'Epic Games Store · скоро бесплатно', 'myst': 'Epic Games Store · игра-сюрприз', 'game': 'Игра', 'until': 'до',
           'today': 'сегодня', 'tomorrow': 'завтра', 'soon_body': '{day} в {time} Epic раздаёт: {names}. Не пропусти 👇',
           'myst_body': '{day} в {time} появится бесплатная игра, название Epic пока скрывает. Раздача идёт около {h} ч, не пропусти 👇', 'open': '📲 Открыть приложение'},
    'en': {'now': 'Epic Games Store · free right now', 'soon': 'Epic Games Store · free soon', 'myst': 'Epic Games Store · mystery game', 'game': 'Game', 'until': 'until',
           'today': 'today', 'tomorrow': 'tomorrow', 'soon_body': '{day} at {time} Epic is giving away: {names}. Do not miss it 👇',
           'myst_body': '{day} at {time} a free game appears, Epic keeps the title hidden for now. It lasts about {h} h, do not miss it 👇', 'open': '📲 Open the app'},
    'sk': {'now': 'Epic Games Store · zadarmo teraz', 'soon': 'Epic Games Store · čoskoro zadarmo', 'myst': 'Epic Games Store · hra-prekvapenie', 'game': 'Hra', 'until': 'do',
           'today': 'dnes', 'tomorrow': 'zajtra', 'soon_body': '{day} o {time} Epic rozdáva: {names}. Nenechaj si ujsť 👇',
           'myst_body': '{day} o {time} sa objaví hra zadarmo, názov Epic zatiaľ skrýva. Trvá asi {h} h, nenechaj si ujsť 👇', 'open': '📲 Otvoriť aplikáciu'},
}

def iso(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))

def loc(d):
    return d.astimezone(TZ)

def fetch():
    cc = {'ua': 'UA', 'sk': 'SK'}.get(CFG.get('deals', {}).get('region', 'ua'), 'UA')
    r = requests.get(URL, params={'locale': 'en-US', 'country': cc, 'allowCountries': cc}, headers=UA, timeout=25)
    r.raise_for_status()
    return r.json()['data']['Catalog']['searchStore']['elements']

def window(e, key):
    for blk in ((e.get('promotions') or {}).get(key) or []):
        for o in blk.get('promotionalOffers') or []:
            if (o.get('discountSetting') or {}).get('discountPercentage') == 0:
                return iso(o['startDate']), iso(o['endDate'])
    return None

def link_of(e):
    slug = None
    for m in (e.get('offerMappings') or []) + ((e.get('catalogNs') or {}).get('mappings') or []):
        if m.get('pageSlug'):
            slug = m['pageSlug']
            break
    slug = slug or e.get('productSlug') or e.get('urlSlug')
    return ('https://store.epicgames.com/p/' + slug.replace('/home', '')) if slug else None

def state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception:
        return {'announced': [], 'teased': []}

def tg(method, **kw):
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/' + method, json=kw, timeout=30)
    return r.json()

def publish(text, label):
    lang = CFG['digest_lang']
    if DRY:
        print('--- [dry] пост в канал ---\n' + text + '\n')
        return True
    res = tg('sendMessage', chat_id=os.environ['CHANNEL'], text=text, parse_mode='HTML', disable_web_page_preview=True,
             reply_markup={'inline_keyboard': [[{'text': TXT[lang]['open'], 'url': os.environ['MINIAPP_LINK']}]]})
    if not res.get('ok'):
        print('канал: ошибка', str(res)[:200])
        return False
    mid = res['result']['message_id']
    try:
        posts = json.loads(POSTS.read_text(encoding='utf-8'))
    except Exception:
        posts = []
    posts.append({'ts': time.strftime('%F %T'), 'message_id': mid, 'label': label})
    POSTS.write_text(json.dumps(posts[-200:], ensure_ascii=False), encoding='utf-8')
    tg('sendMessage', chat_id=os.environ['OWNER_ID'], text='✅ Опубліковано в каналі: ' + label,
       reply_markup={'inline_keyboard': [[{'text': '🗑 Видалити з каналу', 'callback_data': 'dm:' + str(mid)}]]})
    return True

def main():
    lang = CFG['digest_lang']
    tx = TXT[lang]
    cfg = CFG.get('epic_watch', {})
    now = dt.datetime.now(dt.timezone.utc)
    els = fetch()
    st = state()
    cur, soon = [], []
    for e in els:
        w1, w2 = window(e, 'promotionalOffers'), window(e, 'upcomingPromotionalOffers')
        print('лента:', (e.get('title') or '')[:36], '| цена:', ((e.get('price') or {}).get('totalPrice') or {}).get('originalPrice'), '| сейчас:', w1 and (loc(w1[0]).strftime('%d/%m %H:%M') + ' - ' + loc(w1[1]).strftime('%d/%m %H:%M')),
              '| позже:', w2 and (loc(w2[0]).strftime('%d/%m %H:%M') + ' - ' + loc(w2[1]).strftime('%d/%m %H:%M')))
        tp = ((e.get('price') or {}).get('totalPrice')) or {}
        link = link_of(e)
        if w1 and link and tp.get('originalPrice') and tp.get('discountPrice') == 0:
            cur.append((e, link, tp, w1))
        elif w2 and now < w2[0] <= now + dt.timedelta(hours=36) and ((tp.get('originalPrice') or 0) > 0 or 'mystery' in (e.get('title') or '').lower()):
            soon.append((e, link, w2))
    if len(els) > 5 and not DRY:
        live = {x[1] for x in cur}
        gone = []
        def drop(items):
            keep = []
            for o in items:
                if o['source'] == 'epic-games' and o.get('kind') != 'deal' and o['link'] not in live:
                    gone.append(o['title']['ru'])
                    continue
                keep.append(o)
            return keep
        update_offers(drop)
        if gone:
            print('сняты закончившиеся раздачи:', gone)
    if '--seed' in sys.argv:
        print('--seed отключён: он помечает текущие раздачи показанными, не публикуя их')
        return
    if False:
        st['announced'] = sorted(set(st['announced']) | {offer_id(x[1]) for x in cur})
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
        print('отмечены как уже показанные:', [x[0].get('title') for x in cur])
        return
    new = [x for x in cur if offer_id(x[1]) not in st['announced']]
    if new:
        blocks, added = [], []
        for e, link, tp, w in new:
            dec = (tp.get('currencyInfo') or {}).get('decimals', 2)
            sym = CUR.get(tp.get('currencyCode'), tp.get('currencyCode') or '')
            orig = _money(tp['originalPrice'] / 10 ** dec, sym)
            name = e.get('title', '')
            until = loc(w[1]).strftime('%d/%m %H:%M')
            try:
                desc = (e.get('description') or '')[:400]
                bl = make_blurb(name, desc) if (cfg.get('blurb', True) and not DRY) else None
            except Exception:
                bl = None
            end_d = w[1].astimezone(dt.timezone.utc).date().isoformat()
            card = {'category': 'games', 'link': link, 'title': {lang: name}, 'text': {lang: ''}, 'expires_at': end_d, 'blurb': bl,
                    'give': {'game': name, 'store': 'Epic Games Store', 'price': orig, 'until': end_d}}
            blocks.append(dg.block(card, lang, dg.L[lang]))
            d = w[1].astimezone(dt.timezone.utc).date().isoformat()
            ds = d[8:10] + '/' + d[5:7] + '/' + d[:4]
            T = {'uk': 'Безкоштовно в Epic Games Store до {d}. Зазвичай {p}.', 'ru': 'Бесплатно в Epic Games Store до {d}. Обычно {p}.',
                 'en': 'Free on Epic Games Store until {d}. Usually {p}.', 'sk': 'Zadarmo v Epic Games Store do {d}. Zvyčajne {p}.'}
            added.append({'id': offer_id(link), 'title': {l: name for l in T}, 'text': {l: T[l].format(d=ds, p=orig) for l in T}, 'category': 'games',
                          'link': link, 'source': 'epic-games', 'found_at': today().isoformat(), 'approved_at': today().isoformat(), 'expires_at': d,
                          'score': 95, 'worth': tp['originalPrice'] / 10 ** dec, 'status': 'active', 'announced': True,
                          'give': {'game': name, 'store': 'Epic Games Store', 'price': orig, 'until': d}, 'blurb': bl})
        text = '🎁 <b>' + tx['now'] + '</b>\n\n' + '\n\n'.join(blocks)
        if publish(text, ', '.join(a['give']['game'] for a in added)) and not DRY:
            def apply(cur_items):
                by = {o['id']: o for o in cur_items}
                for a in added:
                    if a['id'] in by:
                        by[a['id']]['announced'] = True
                    else:
                        cur_items.append(a)
            update_offers(apply)
            st['announced'] = sorted(set(st['announced']) | {a['id'] for a in added})
    if cfg.get('teasers', True) and soon:
        groups = {}
        for e, link, w in soon:
            groups.setdefault(w[0].isoformat(), []).append((e, link, w))
        for key, items in groups.items():
            if key in st['teased']:
                continue
            start, end = items[0][2]
            local = loc(start)
            day = tx['today'] if local.date() == loc(now).date() else tx['tomorrow']
            real = [html.escape(e.get('title', '')) for e, link, w in items if link and 'mystery' not in (e.get('title') or '').lower()]
            if real:
                text = '🔜 <b>' + tx['soon'] + '</b>\n\n' + tx['soon_body'].format(day=day, time=local.strftime('%H:%M'), names=', '.join('<b>' + n + '</b>' for n in real))
            else:
                text = '🕵️ <b>' + tx['myst'] + '</b>\n\n' + tx['myst_body'].format(day=day, time=local.strftime('%H:%M'), h=round((end - start).total_seconds() / 3600))
            if publish(text, 'анонс ' + key[:16]) and not DRY:
                st['teased'].append(key)
    if not DRY:
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    print('готово: новых раздач', len(new), '| ближайших', len(soon))

main()
