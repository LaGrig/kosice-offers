import argparse, datetime as dt, sys
sys.path.insert(0, 'scripts')
from common import load_offers, update_offers, offer_id, today
from llm import ask_llm
from textfix import nums

LANGS = ('uk', 'ru', 'en', 'sk')
SYS = ('Переведи заголовок и текст на uk, ru, en, sk. Сохрани смысл, числа, названия и ссылки без изменений, ничего не добавляй. '
       'Ответь ТОЛЬКО JSON: {"title": {"uk": "", "ru": "", "en": "", "sk": ""}, "text": {"uk": "", "ru": "", "en": "", "sk": ""}}')

def translate(title, text, lang):
    out = ask_llm('writer', {'source_lang': lang, 'title': title, 'text': text}, retries=0, system=SYS)
    try:
        for k, src in (('title', title), ('text', text)):
            for l in LANGS:
                if not out[k].get(l) or nums(out[k][l]) != nums(src):
                    return None
        return out
    except Exception:
        return None

a = sys.argv[1:] or ['list']
if a[0] == 'list':
    for o in sorted(load_offers(), key=lambda o: o.get('approved_at') or o['found_at']):
        print(o['id'], o['status'][:4], (o.get('kind') or 'give')[:4], o['source'][:10], o.get('expires_at') or ('pin' if o.get('pinned') else '-'), '|', o['title']['ru'][:40])
elif a[0] in ('rm', 'hide', 'show'):
    ids = set(a[1:])
    def apply(cur):
        if a[0] == 'rm':
            return [o for o in cur if o['id'] not in ids]
        for o in cur:
            if o['id'] in ids:
                o['status'] = 'hidden' if a[0] == 'hide' else 'active'
    update_offers(apply)
    print(a[0], ids)
elif a[0] == 'set' and len(a) == 5:
    _, oid, field, lang, val = a
    def apply(cur):
        for o in cur:
            if o['id'] == oid:
                for l in (LANGS if lang == 'all' else (lang,)):
                    o[field][l] = val
    update_offers(apply)
    print('изменено', oid, field, lang)
elif a[0] == 'add':
    ap = argparse.ArgumentParser(prog='admin.py add')
    ap.add_argument('--title', required=True)
    ap.add_argument('--text', required=True)
    ap.add_argument('--link', required=True)
    ap.add_argument('--cat', default='other')
    ap.add_argument('--until', help='срок YYYY-MM-DD (обязателен, если нет --pin)')
    ap.add_argument('--pin', action='store_true', help='без срока, не снимается автоматически')
    ap.add_argument('--lang', default='uk')
    ns = ap.parse_args(a[1:])
    if not ns.pin and not ns.until:
        sys.exit('нужен --until YYYY-MM-DD или --pin')
    if ns.until:
        dt.date.fromisoformat(ns.until)
    tr = translate(ns.title, ns.text, ns.lang)
    if not tr:
        print('перевод не прошёл проверку: везде будет исходный текст')
        tr = {'title': {l: ns.title for l in LANGS}, 'text': {l: ns.text for l in LANGS}}
    card = {'id': offer_id(ns.link + '|' + ns.title), 'title': tr['title'], 'text': tr['text'], 'category': ns.cat, 'link': ns.link, 'source': 'manual',
            'found_at': today().isoformat(), 'approved_at': today().isoformat(), 'expires_at': ns.until, 'score': 90, 'status': 'active', 'pinned': bool(ns.pin)}
    update_offers(lambda cur: cur.append(card) if not any(o['id'] == card['id'] for o in cur) else None)
    print('добавлено:', card['id'], '|', tr['title']['uk'])
else:
    print('list | rm ID... | hide ID... | show ID... | set ID title|text uk|ru|en|sk|all "текст" | add --title ... --text ... --link ... --until YYYY-MM-DD [--cat games] [--lang uk] | add ... --pin')
