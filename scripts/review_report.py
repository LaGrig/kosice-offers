import datetime as dt, html, json, os, sys, requests
from collections import Counter
from common import today
from autolog import F

API = 'https://api.telegram.org/bot' + os.environ['BOT_TOKEN']
NEAR = ('itch:', 'цена', 'отклонено')
KINDS = ('не релевантно', 'срок истёк', 'ссылка', 'itch:', 'цена', 'отклонено', 'Steam')

def kind(why):
    return next((k for k in KINDS if why.startswith(k)), 'другое')

def send(text, kb=None):
    body = {'chat_id': os.environ['OWNER_ID'], 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if kb:
        body['reply_markup'] = kb
    return requests.post(API + '/sendMessage', json=body, timeout=30).status_code

def main():
    show_all = '--all' in sys.argv
    rows = [json.loads(l) for l in F.read_text(encoding='utf-8').splitlines() if l.strip()] if F.exists() else []
    new = [r for r in rows if not r.get('reported')]
    cutoff = (today() - dt.timedelta(days=2)).isoformat()
    pool = [r for r in rows if r['date'] >= cutoff] if show_all else new
    if not pool:
        print('нечего показывать')
        return
    cnt = Counter(kind(r['why']) for r in pool)
    send('🔎 <b>Отсеяно редакцией: ' + str(len(pool)) + '</b>\n' + '\n'.join(k + ': ' + str(n) for k, n in cnt.most_common()))
    cand = [r for r in pool if show_all or r['why'].startswith(NEAR)][:15 if show_all else 8]
    for r in cand:
        text = ('<b>' + html.escape(r['title'][:90]) + '</b>\n' + html.escape(r['why'][:200])
                + '\n' + r['source'] + ' · цена ' + str(r['item'].get('worth') or '?'))
        kb = {'inline_keyboard': [[{'text': '↩️ Вернуть', 'callback_data': 'rs:' + r['id']}, {'text': '🔗 Оригинал', 'url': r['link']}]]}
        print(r['id'], send(text, kb))
    for r in new:
        r['reported'] = True
    F.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')

main()
