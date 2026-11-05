import re
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
- Не смешивай языки. Название игры не пиши в тексте.
Примеры тона (про выдуманные игры):
- описание «Кооперативная ферма: днём выращиваешь урожай, ночью отбиваешься от монстров» -> uk: «Вдень сієш, вночі відбиваєшся від монстрів, і краще це робити з другом»
- описание «Головоломка про кота, который ищет выход из лабиринта» -> ru: «Расслабляющий пазл, где ты помогаешь коту выбраться из лабиринта»
Ответь ТОЛЬКО JSON: {"uk": "", "ru": "", "en": "", "sk": ""}'''

VERIFY = '''Ты проверяешь короткую реплику об игре. Тебе дают описание игры и реплику на нескольких языках.
Определи, есть ли в реплике утверждения, которых нет в описании: жанр, сюжет, персонажи, графика, сложность, режимы игры, место действия.
Ответь ТОЛЬКО JSON: {"ok": true или false, "unsupported": ["что именно выдумано"]}'''

BAN = re.compile(r'(?i)(оновлен|обновлен|update|edition|видан|издан|скидк|знижк|бесплат|безкошт|раздач|роздач|\bfree\b|zadarmo|zľav|\bsale\b|discount|₴|\$|€)')
CYR = re.compile('[А-Яа-яІіЇїЄєҐґ]')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2190-\u27BF\u2B00-\u2BFF\uFE0F\u200d]')
BAD_START = re.compile(r'(?i)^(тут|здесь|here|tu|toto)\b')

def clean(s):
    v = ' '.join(EMOJI.sub('', s).split())
    return v[:1].upper() + v[1:]

def supported(desc, res):
    out = ask_llm('qa', {'description': desc, 'blurb': res}, retries=0, system=VERIFY)
    return isinstance(out, dict) and out.get('ok') is True

def make_blurb(game, desc):
    desc = ' '.join((desc or '').split())[:500]
    if len(desc) < 20:
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
