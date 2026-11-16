import re, requests
from common import CFG
from llm import ask_llm
from textfix import nums

SYSTEM = '''Ты — друг-студент, который коротко рассказывает другу, о чём игра и чем она цепляет. Тебе дают название, жанры и описание игры.
Напиши ОДНУ короткую фразу (до 120 символов) на каждом из языков: uk, ru, en, sk. Как в переписке между друзьями: просто и тепло, на «ты», без канцелярита и рекламных штампов.
Формат строго: «<Жанр>: <коротко что делаешь в игре>» (жанр с большой буквы, затем двоеточие и продолжение со строчной буквы).
Примеры:
- «Покрокова стратегія: завойовуєш землі Нового Світу та ведеш масштабні битви»
- «Мотогонки: гоняешь по реальным трассам на бешеной скорости»
- «Turn-based strategy: conquer the New World and lead massive battles»
- «Ťahová stratégia: dobývaš Nový svet a vedieš masívne bitky»
Правила:
- Опирайся на название, теги жанров (Genres:) и описание. Указывай точный жанр игры (например: RPG, Экшен-RPG, Стратегия, Пошаговая стратегия, Шутер, Гонки, Мотогонки, Симулятор, Файтинг, Приключение, Экшен, MMORPG, Рогалик). Не выдумывай сюжет, персонажей, графику, сложность или режимы, которых нет в описании.
- Не упоминай цену, скидку, бесплатность, раздачу, сроки и любые числа (кроме тех, что есть в описании).
- Не начинай фразу словами «тут», «здесь», «here». Не используй слова «шедевр», «культовый», «must have», «обновление», «версия», «издание», «дополнение».
- Без эмодзи и без восклицательных знаков. После двоеточия пиши от второго лица в настоящем времени («Собираешь команду» со строчной после двоеточия).
- Не называй реальные страны, города и национальности: пиши нейтрально.
- Расскажи об игре в целом, а не об одном режиме или дополнении. Если описание про дополнение, набор, апгрейд или бонусный контент, либо по нему нельзя понять суть игры, верни пустые строки во всех языках.
- Не смешивай языки. Название игры не пиши в тексте.
Ответь ТОЛЬКО JSON: {"uk": "", "ru": "", "en": "", "sk": ""}'''

VERIFY = '''Ты проверяешь короткую реплику об игре в формате «Жанр: описание». Тебе дают название игры, теги Genres и описание, а также реплику на нескольких языках.
Называть жанр игры, который следует из тегов Genres, названия игры или описания (например: RPG, экшен-RPG, стратегия, гонки, мотогонки, шутер, симулятор, файтинг, приключение), — РАЗРЕШЕНО.
Определи, есть ли в реплике выдуманные факты о сюжете, персонажах, графике, сложности, режимах игры или месте действия, которых нет в описании.
Ответь ТОЛЬКО JSON: {"ok": true или false, "unsupported": ["что именно выдумано"]}'''

BAN = re.compile(r'(?i)(москв|moscow|росі[яйї]|росси|russia|оновлен|обновлен|update|edition|видан|издан|скидк|знижк|бесплат|безкошт|раздач|роздач|\bfree\b|zadarmo|zľav|\bsale\b|discount|₴|\$|€)')
CYR = re.compile('[А-Яа-яІіЇїЄєҐґ]')
CJK = re.compile(r'[\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2190-\u27BF\u2B00-\u2BFF\uFE0F\u200d]')
BAD_START = re.compile(r'(?i)^(тут|здесь|here|tu|toto)\b')

def clean(s):
    v = ' '.join(EMOJI.sub('', s).split())
    if ':' not in v:
        for sep in (' — ', ' – ', ' - '):
            if sep in v:
                v = v.replace(sep, ': ', 1)
                break
    return v[:1].upper() + v[1:]

def supported(desc, res, game=None):
    payload = {'description': desc, 'blurb': res}
    if game:
        payload['game'] = game
    out = ask_llm('qa', payload, retries=1, system=VERIFY)
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
        genres = [g['description'] for g in (d.get('genres') or []) if g.get('description')]
        pref = ('Genres: ' + ', '.join(genres) + '. ') if genres else ''
        sd = ' '.join((d.get('short_description') or '').split())
        if len(sd) >= 50 and not DLC_RE.search(sd):
            return (pref + sd)[:550]
        raw = re.sub(r'<[^>]+>', ' ', d.get('about_the_game') or d.get('detailed_description') or '')
        about = ' '.join(raw.split())
        if len(about) >= 50 and not DLC_RE.search(about[:300]):
            return (pref + about)[:550]
        return (pref + sd)[:550]
    except Exception:
        return ''

def make_blurb(game, desc):
    desc = ' '.join((desc or '').split())[:550]
    if 'Genres:' not in desc or len(desc) < 80 or DLC_RE.search(desc):
        fb = steam_desc_by_name(game)
        if fb and not DLC_RE.search(fb):
            if len(desc) < 60 or DLC_RE.search(desc):
                if len(fb) >= 25:
                    desc = fb
            elif fb.startswith('Genres:'):
                gline = fb.split('. ', 1)[0] + '. '
                desc = (gline + desc)[:550]
    if len(desc) < 20 or DLC_RE.search(desc):
        return None
    allowed = nums(game + ' ' + desc)
    for attempt in range(3):
        out = ask_llm('writer', {'game': game, 'description': desc}, retries=1, system=SYSTEM)
        if not isinstance(out, dict):
            continue
        res, ok = {}, True
        for lang in ('uk', 'ru', 'en', 'sk'):
            raw = str(out.get(lang, ''))
            v = clean(raw)
            if not v or ':' not in v or len(v) > 160 or '\n' in raw or BAN.search(v) or (nums(v) - allowed) or BAD_START.search(v) or CJK.search(v):
                ok = False
                break
            if (lang in ('uk', 'ru')) != bool(CYR.search(v)):
                ok = False
                break
            res[lang] = v
        if not ok:
            continue
        if CFG.get('blurb_verify', True) and not supported(desc, res, game=game):
            continue
        return res
    return None
