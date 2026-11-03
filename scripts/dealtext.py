import re, zlib

T = {
    'uk': {'in': 'У топі {store}: {parts}.', 's': '№{n} за продажами', 'p': '№{n} за онлайном',
           'body': '{game} у {store} зараз за {new} замість {old}.',
           'tails': ['Гарний момент забрати 🎮', 'Саме час додати до бібліотеки 🎮', 'Не пропусти 🎮', 'Студентський бюджет скаже дякую 🎮']},
    'ru': {'in': 'В топе {store}: {parts}.', 's': '№{n} по продажам', 'p': '№{n} по онлайну',
           'body': '{game} в {store} сейчас за {new} вместо {old}.',
           'tails': ['Хороший момент забрать 🎮', 'Самое время добавить в библиотеку 🎮', 'Не пропусти 🎮', 'Студенческий бюджет скажет спасибо 🎮']},
    'en': {'in': 'In the {store} charts: {parts}.', 's': '#{n} bestseller', 'p': '#{n} most played',
           'body': '{game} on {store} is {new} instead of {old} right now.',
           'tails': ['A good moment to grab it 🎮', 'Time to add it to your library 🎮', "Don't miss it 🎮", 'Your student budget will thank you 🎮']},
    'sk': {'in': 'V rebríčku {store}: {parts}.', 's': '#{n} podľa predajov', 'p': '#{n} podľa online',
           'body': '{game} v {store} je teraz za {new} namiesto {old}.',
           'tails': ['Dobrý čas ju chytiť 🎮', 'Čas pridať ju do knižnice 🎮', 'Nenechaj si ujsť 🎮', 'Tvoj študentský rozpočet poďakuje 🎮']},
}

def clean_game(name):
    s = re.sub(r'[™®©]', '', name or '')
    s = re.sub(r'\s*[-–:]?\s*\(?\b(standard|digital|definitive|deluxe|complete|ultimate|gold|premium)\s+edition\)?\s*$', '', s, flags=re.I)
    return ' '.join(s.split())

def deal_post(item):
    d = item['deal']
    game = clean_game(d['game'])
    k = zlib.crc32(game.encode('utf-8'))
    title, text = {}, {}
    for lang, t in T.items():
        parts = []
        if d.get('rank_sales'):
            parts.append(t['s'].format(n=d['rank_sales']))
        if d.get('rank_play'):
            parts.append(t['p'].format(n=d['rank_play']))
        body = t['body'].format(game=game, store=d['store'], new=d['new'], old=d['old'])
        if parts:
            body += ' ' + t['in'].format(store=d['store'], parts=', '.join(parts))
        text[lang] = body + ' ' + t['tails'][k % len(t['tails'])]
        title[lang] = game + ' −' + str(d['pct']) + '%'
    return {'title': title, 'text': text}
