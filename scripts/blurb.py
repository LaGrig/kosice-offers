import re, requests
from common import CFG
from llm import ask_llm
from textfix import nums

SYSTEM = '''Ты — друг-студент, который коротко рассказывает другу, о чём игра и чем она цепляет. Тебе дают название и описание игры.
Напиши ОДНУ короткую фразу (до 100 символов) на каждом из языков: uk, ru, en, sk. Как в переписке между друзьями: просто и тепло, на «ты», без канцелярита и рекламных штампов.
Правила:
- Опирайся только на описание. Не придумывай жанр, сюжет, персонажей, графику, сложность, режимы, рейтинг, число игроков, платформы.
- Не упоминай цену, скидку, бесплатность, раздачу, сроки и любые числа.
- Не начинай фразу словами «тут», «здесь», «here». Не используй слова «шедевр», «культовый», «must have».
- Без эмодзи и без восклицательных знаков. Пиши от второго лица в настоящем времени, как рассказываешь другу: «Выживаешь в городе», «Собираешь оружие», «Стреляешь вместе с друзьями». Начинай с большой буквы.
- Не используй слова «обновление», «версия», «издание», «дополнение».
- Не называй реальные страны, города и национальности (Москва, Россия и т.п.): пиши нейтрально, например «метро» или «постапокалиптическая пустошь».
- Расскажи об игре в целом, а не об одном режиме или дополнении. Если описание про дополнение, набор, апгрейд или бонусный контент, либо по нему нельзя понять суть игры, верни пустые строки во всех языках.
- Не смешивай языки. Название игры не пиши в тексте.
Примеры тона (про выдуманные игры):
- описание «Кооперативная ферма: днём выращиваешь урожай, ночью отбиваешься от монстров» -> uk: «Вдень сієш, вночі відбиваєшся від монстрів, і краще це робити з другом»
- описание «Головоломка про кота, который ищет выход из лабиринта» -> ru: «Расслабляющий пазл, где ты помогаешь коту выбраться из лабиринта»
Ответь ТОЛЬКО JSON: {"uk": "", "ru": "", "en": "", "sk": ""}'''

VERIFY = '''Ты проверяешь короткую реплику об игре. Тебе дают описание игры и реплику на нескольких языках.
Определи, есть ли в реплике утверждения, которых нет в описании: жанр, сюжет, персонажи, графика, сложность, режимы игры, место действия.
Ответь ТОЛЬКО JSON: {"ok": true или false, "unsupported": ["что именно выдумано"]}'''

BAN = re.compile(r'(?i)(москв|moscow|росі[яйї]|росси|russia|оновлен|обновлен|update|edition|видан|издан|скидк|знижк|бесплат|безкошт|раздач|роздач|\bfree\b|zadarmo|zľav|\bsale\b|discount|₴|\$|€)')
CYR = re.compile('[А-Яа-яІіЇїЄєҐґ]')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2190-\u27BF\u2B00-\u2BFF\uFE0F\u200d]')
BAD_START = re.compile(r'(?i)^(тут|здесь|here|tu|toto)\b')

def clean(s):
    v = ' '.join(EMOJI.sub('', s).split())
    return v[:1].upper() + v[1:]

def supported(desc, res):
    out = ask_llm('qa', {'description': desc, 'blurb': res}, retries=0, system=VERIFY)
    return isinstance(out, dict) and out.get('ok') is True

DLC_RE = re.compile(r'(?i)\b(upgrade|dlc|season pass|add-?on|expansion pack|bonus content|soundtrack)\b')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def _clean_title(name):
    s = re.sub(r'[™®©]', '', name or '')
    s = re.sub(r'\s*[-–:]?\s*\(?\b(standard|digital|definitive|deluxe|complete|ultimate|gold|premium)\s+edition\)?\s*$', '', s, flags=re.I)
    return ' '.join(s.split())

def steam_desc_by_name(game):
    q = _clean_title(game)
    if not q:
        return ''
    try:
        r = requests.get('https://store.steampowered.com/search/results/',
                         params={'term': q, 'json': 1}, headers=UA, timeout=15)
        if r.status_code != 200:
            return ''
        items = (r.json() or {}).get('items') or []
        app = None
        for it in items:
            nm = (it.get('name') or '').lower()
            if 'demo' in nm or 'soundtrack' in nm:
                continue
            m = re.search(r'/apps?/(\d+)/', it.get('logo') or '')
            if m:
                app = m.group(1)
                break
        if not app:
            m = re.search(r'/apps?/(\d+)/', r.text)
            app = m.group(1) if m else None
        if not app:
            return ''
        d = requests.get('https://store.steampowered.com/api/appdetails',
                         params={'appids': app, 'l': 'english', 'cc': 'us'},
                         headers=UA, timeout=15).json().get(str(app), {}).get('data') or {}
        if d.get('type') != 'game':
            return ''
        sd = ' '.join((d.get('short_description') or '').split())
        if len(sd) >= 50 and not DLC_RE.search(sd):
            return sd[:500]
        raw = re.sub(r'<[^>]+>', ' ', d.get('about_the_game') or d.get('detailed_description') or '')
        about = ' '.join(raw.split())
        if len(about) >= 50 and not DLC_RE.search(about[:300]):
            return about[:500]
        return sd[:500]
    except Exception:
        return ''

def make_blurb(game, desc):
    desc = ' '.join((desc or '').split())[:500]
    if len(desc) < 60 or DLC_RE.search(desc):
        fb = steam_desc_by_name(game)
        if fb and len(fb) >= 25 and not DLC_RE.search(fb):
            desc = fb
    if len(desc) < 20 or DLC_RE.search(desc):
        return None
    allowed = nums(game + ' ' + desc)
    for attempt in range(2):
        out = ask_llm('writer', {'game': game, 'description': desc}, retries=0, system=SYSTEM)
        if not isinstance(out, dict):
            continue
        res, ok = {}, True
        for lang in ('uk', 'ru', 'en', 'sk'):
            raw = str(out.get(lang, ''))
            v = clean(raw)
            if not v or len(v) > 140 or '\n' in raw or BAN.search(v) or (nums(v) - allowed) or BAD_START.search(v):
                ok = False
                break
            if (lang in ('uk', 'ru')) != bool(CYR.search(v)):
                ok = False
                break
            res[lang] = v
        if not ok:
            continue
        if CFG.get('blurb_verify', True) and not supported(desc, res):
            continue
        return res
    return None
