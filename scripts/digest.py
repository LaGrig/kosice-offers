import html, os, requests
from common import CFG, load_offers, today

def main():
    t = today().isoformat()
    items = [o for o in load_offers() if o['status'] == 'active' and o['found_at'] == t]
    items.sort(key=lambda o: -o['score'])
    top = [o for o in items if o['score'] >= CFG['digest_threshold']][:CFG['digest_size']]
    if len(top) < 3:
        top = items[:3]
    if not top:
        print('нечего публиковать')
        return
    lang = CFG['digest_lang']
    parts = ['<b>Находки дня</b>']
    for o in top:
        parts.append('<b>' + html.escape(o['title'][lang]) + '</b>\n' + html.escape(o['text'][lang]))
    body = {
        'chat_id': os.environ['CHANNEL'],
        'text': '\n\n'.join(parts),
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
        'reply_markup': {'inline_keyboard': [[{'text': 'Все предложения', 'url': os.environ['MINIAPP_LINK']}]]},
    }
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:300])

main()
