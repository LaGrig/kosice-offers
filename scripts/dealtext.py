import re, zlib

T = {
    'uk': {'body': '{game} у {store} зараз за {new} замість {old}.',
           'tails': ['Гарний момент забрати 🎮', 'Саме час додати до бібліотеки 🎮', 'Не пропусти 🎮', 'Студентський бюджет скаже дякую 🎮']},
    'ru': {'body': '{game} в {store} сейчас за {new} вместо {old}.',
           'tails': ['Хороший момент забрать 🎮', 'Самое время добавить в библиотеку 🎮', 'Не пропусти 🎮', 'Студенческий бюджет скажет спасибо 🎮']},
    'en': {'body': '{game} on {store} is {new} instead of {old} right now.',
           'tails': ['A good moment to grab it 🎮', 'Time to add it to your library 🎮', "Don't miss it 🎮", 'Your student budget will thank you 🎮']},
    'sk': {'body': '{game} v {store} je teraz za {new} namiesto {old}.',
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
        body = t['body'].format(game=game, store=d['store'], new=d['new'], old=d['old'])
        text[lang] = body + ' ' + t['tails'][k % len(t['tails'])]
        title[lang] = game
    return {'title': title, 'text': text}
