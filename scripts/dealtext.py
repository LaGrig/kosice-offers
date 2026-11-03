T = {
    'uk': {'in': 'У топі {store}: {parts}.', 's': '№{n} за продажами', 'p': '№{n} за онлайном',
           'body': '{game} у {store} зараз за {new} замість {old}.', 'tail': 'Гарний момент забрати 🎮'},
    'ru': {'in': 'В топе {store}: {parts}.', 's': '№{n} по продажам', 'p': '№{n} по онлайну',
           'body': '{game} в {store} сейчас за {new} вместо {old}.', 'tail': 'Хороший момент забрать 🎮'},
    'en': {'in': 'In the {store} charts: {parts}.', 's': '#{n} bestseller', 'p': '#{n} most played',
           'body': '{game} on {store} is {new} instead of {old} right now.', 'tail': 'A good moment to grab it 🎮'},
    'sk': {'in': 'V rebríčku {store}: {parts}.', 's': '#{n} podľa predajov', 'p': '#{n} podľa online',
           'body': '{game} v {store} je teraz za {new} namiesto {old}.', 'tail': 'Dobrý čas ju chytiť 🎮'},
}

def deal_post(item):
    d = item['deal']
    title, text = {}, {}
    for lang, t in T.items():
        parts = []
        if d.get('rank_sales'):
            parts.append(t['s'].format(n=d['rank_sales']))
        if d.get('rank_play'):
            parts.append(t['p'].format(n=d['rank_play']))
        body = t['body'].format(game=d['game'], store=d['store'], new=d['new'], old=d['old'])
        if parts:
            body += ' ' + t['in'].format(store=d['store'], parts=', '.join(parts))
        text[lang] = body + ' ' + t['tail']
        title[lang] = d['game'] + ' −' + str(d['pct']) + '%'
    return {'title': title, 'text': text}
