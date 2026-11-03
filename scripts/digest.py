import datetime as dt, html, json, os, requests
from common import CFG, ROOT, load_offers, today
from givefmt import norm_price

L = {
    'uk': {'head': 'Знахідки дня', 'sub': 'Забирай, поки діє 👇', 'free': 'Безкоштовно', 'usual': 'зазвичай', 'until': 'до',
           's': '№{n} за продажами', 'p': '№{n} за онлайном', 'more': 'Ще {n} пропозицій у застосунку', 'open': '📲 Відкрити застосунок'},
    'ru': {'head': 'Находки дня', 'sub': 'Забирай, пока действует 👇', 'free': 'Бесплатно', 'usual': 'обычно', 'until': 'до',
           's': '№{n} по продажам', 'p': '№{n} по онлайну', 'more': 'Ещё {n} предложений в приложении', 'open': '📲 Открыть приложение'},
    'en': {'head': 'Finds of the day', 'sub': 'Grab them while they last 👇', 'free': 'Free', 'usual': 'usually', 'until': 'until',
           's': '#{n} bestseller', 'p': '#{n} most played', 'more': '{n} more offers in the app', 'open': '📲 Open the app'},
    'sk': {'head': 'Objavy dňa', 'sub': 'Chyť ich, kým platia 👇', 'free': 'Zadarmo', 'usual': 'zvyčajne', 'until': 'do',
           's': '#{n} podľa predajov', 'p': '#{n} podľa online', 'more': 'Ďalších {n} ponúk v aplikácii', 'open': '📲 Otvoriť aplikáciu'},
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
    if len(text) <= 220:
        return text
    cut = text.find('. ')
    return (text if cut == -1 else text[:cut + 1])[:160]

def name_link(o, name):
    return '<a href="' + html.escape(o['link'], quote=True) + '"><b>' + esc(name) + '</b></a>'

def block(o, lang):
    tx = L[lang]
    d, g = o.get('deal'), o.get('give')
    if d:
        out = '💸 ' + name_link(o, d['game']) + ' · <b>−' + str(d['pct']) + '%</b>\n' + esc(d['old']) + ' → <b>' + esc(d['new']) + '</b> · ' + esc(d['store'])
        tops = []
        if d.get('rank_sales'):
            tops.append(tx['s'].format(n=d['rank_sales']))
        if d.get('rank_play'):
            tops.append(tx['p'].format(n=d['rank_play']))
        return out + ('\n🏆 ' + ' · '.join(tops) if tops else '')
    if g:
        bits = [tx['free'] + ' · ' + g['store']]
        if g.get('price'):
            bits.append(tx['usual'] + ' ' + norm_price(g['price']))
        if g.get('until'):
            bits.append(tx['until'] + ' ' + short(g['until']))
        return '🎁 ' + name_link(o, g['game']) + '\n' + esc(' · '.join(bits))
    out = '✨ ' + name_link(o, o['title'][lang]) + '\n' + esc(hook(o['text'][lang]))
    return out + ('\n⏳ ' + tx['until'] + ' ' + short(o['expires_at']) if o.get('expires_at') else '')

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
    parts = ['🔥 <b>' + tx['head'] + '</b> · ' + short(t) + '\n<i>' + tx['sub'] + '</i>'] + [block(o, lang) for o in top]
    preview = bool(os.environ.get('DIGEST_CHAT'))
    body = {'chat_id': os.environ.get('DIGEST_CHAT') or os.environ['CHANNEL'], 'text': '\n\n'.join(parts), 'parse_mode': 'HTML',
            'disable_web_page_preview': True, 'reply_markup': {'inline_keyboard': [[{'text': tx['open'], 'url': os.environ['MINIAPP_LINK']}]]}}
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:200])
    if r.status_code == 200 and not preview:
        SENT.write_text(json.dumps(sorted(load_sent() | ids)))

main()
