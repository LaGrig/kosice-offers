import html, os, requests
from collections import Counter
from common import CFG, load_offers, today

T = {
    'uk': {'head': 'Знахідки дня', 'until': 'до', 'more': 'У застосунку ще', 'unit': 'пропозицій', 'open': '📲 Відкрити застосунок'},
    'ru': {'head': 'Находки дня', 'until': 'до', 'more': 'В приложении ещё', 'unit': 'предложений', 'open': '📲 Открыть приложение'},
    'en': {'head': 'Finds of the day', 'until': 'until', 'more': 'More in the app:', 'unit': 'offers', 'open': '📲 Open the app'},
    'sk': {'head': 'Objavy dňa', 'until': 'do', 'more': 'V aplikácii je ešte', 'unit': 'ponúk', 'open': '📲 Otvoriť aplikáciu'},
}
EMOJI = {'food': '🍔', 'games': '🎮', 'events': '🎟', 'places': '📍', 'it_soft': '💻', 'services': '🧾', 'jobs': '💼', 'study': '🎓', 'other': '✨'}
NAMES = {
    'uk': {'food': 'Їжа', 'games': 'Ігри', 'events': 'Події', 'places': 'Місця', 'it_soft': 'IT і софт', 'services': 'Сервіси', 'jobs': 'Робота', 'study': 'Навчання', 'other': 'Інше'},
    'ru': {'food': 'Еда', 'games': 'Игры', 'events': 'События', 'places': 'Места', 'it_soft': 'IT и софт', 'services': 'Сервисы', 'jobs': 'Работа', 'study': 'Учёба', 'other': 'Другое'},
    'en': {'food': 'Food', 'games': 'Games', 'events': 'Events', 'places': 'Places', 'it_soft': 'IT & software', 'services': 'Services', 'jobs': 'Jobs', 'study': 'Study', 'other': 'Other'},
    'sk': {'food': 'Jedlo', 'games': 'Hry', 'events': 'Udalosti', 'places': 'Miesta', 'it_soft': 'IT a softvér', 'services': 'Služby', 'jobs': 'Práca', 'study': 'Štúdium', 'other': 'Iné'},
}

def hook(text):
    text = ' '.join(text.split())
    cut = text.find('. ')
    first = text if cut == -1 else text[:cut + 1]
    return first[:160]

def short(d):
    return d[8:10] + '.' + d[5:7]

def main():
    t = today().isoformat()
    lang = CFG['digest_lang']
    tx = T[lang]
    link = os.environ['MINIAPP_LINK']
    active = [o for o in load_offers() if o['status'] == 'active' and (not o.get('expires_at') or o['expires_at'] >= t)]
    fresh = [o for o in active if (o.get('approved_at') or o['found_at']) == t]
    fresh.sort(key=lambda o: -o['score'])
    top = [o for o in fresh if o['score'] >= CFG['digest_threshold']][:CFG['digest_size']]
    if len(top) < 3:
        top = fresh[:3]
    if not top:
        print('нечего публиковать')
        return
    ids = {o['id'] for o in top}
    parts = ['🔥 <b>' + tx['head'] + '</b> · ' + today().strftime('%d.%m')]
    for o in top:
        line = EMOJI.get(o['category'], '✨') + ' <a href="' + html.escape(o['link'], quote=True) + '"><b>' + html.escape(o['title'][lang]) + '</b></a>\n'
        line += '<blockquote>' + html.escape(hook(o['text'][lang])) + '</blockquote>'
        if o.get('expires_at'):
            line += '\n⏳ ' + tx['until'] + ' ' + short(o['expires_at'])
        parts.append(line)
    rest = [o for o in active if o['id'] not in ids]
    buttons = [[{'text': tx['open'], 'url': link}]]
    if rest:
        parts.append('━━━━━━━━━━\n📲 ' + tx['more'] + ' <b>' + str(len(rest)) + '</b> ' + tx['unit'])
        counts = Counter(o['category'] for o in rest).most_common(3)
        buttons.append([{'text': EMOJI.get(c, '✨') + ' ' + NAMES[lang].get(c, c) + ' · ' + str(n), 'url': link + '?startapp=' + c} for c, n in counts])
    body = {
        'chat_id': os.environ.get('DIGEST_CHAT') or os.environ['CHANNEL'],
        'text': '\n\n'.join(parts),
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
        'reply_markup': {'inline_keyboard': buttons},
    }
    r = requests.post('https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', json=body, timeout=30)
    print(r.status_code, r.text[:300])

main()
