import html, json, os, requests
from common import CFG, ROOT, load_offers

SENT = ROOT / 'data' / 'review_sent.json'
API = 'https://api.telegram.org/bot' + os.environ['BOT_TOKEN']

def sent_ids():
    if SENT.exists():
        return set(json.loads(SENT.read_text()))
    return set()

def main():
    owner = os.environ['OWNER_ID']
    lang = CFG['digest_lang']
    done = sent_ids()
    for o in load_offers():
        if o['status'] != 'pending' or o['id'] in done:
            continue
        text = ('<b>' + html.escape(o['title'][lang]) + '</b>\n' + html.escape(o['text'][lang])
                + '\n\n' + o['category'] + ' · ⭐ ' + str(o['score']) + ' · ⏳ ' + str(o.get('expires_at') or '—') + ' · ' + o['source'] + ' · цена ' + str(o.get('worth') or '?'))
        kb = {'inline_keyboard': [
            [{'text': '✅ Публикуем', 'callback_data': 'ok:' + o['id']}, {'text': '❌ Отмена', 'callback_data': 'no:' + o['id']}],
            [{'text': '🔗 Оригинал', 'url': o['link']}],
        ]}
        r = requests.post(API + '/sendMessage', json={'chat_id': owner, 'text': text, 'parse_mode': 'HTML',
                          'disable_web_page_preview': True, 'reply_markup': kb}, timeout=30)
        print(o['id'], r.status_code)
        if r.status_code == 200:
            done.add(o['id'])
    SENT.write_text(json.dumps(sorted(done)))

main()
