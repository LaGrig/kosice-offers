import sys
sys.path.insert(0, 'scripts')
from common import today
from llm import ask_llm, models_for

def mk(uk, ru, en, sk):
    return {'uk': uk, 'ru': ru, 'en': en, 'sk': sk}

SCOUT = [
    ({'title': "Sorry We're Closed", 'summary': "Epic Games Store: бесплатная раздача игры Sorry We're Closed. Обычная цена 459₴. Бесплатно до 2026-11-05.", 'link': 'https://store.epicgames.com/p/x', 'source': 'epic-games'}, True),
    ({'title': 'Cozy Frog Clicker - free browser game', 'summary': 'A free browser game, always free to play, no sale or giveaway.', 'link': 'https://example.com/frog', 'source': 'reddit'}, False),
    ({'title': 'Free Steam keys of SomeGame', 'summary': 'Enter the giveaway on Gleam: follow, retweet and complete tasks for a chance to win a key.', 'link': 'https://gleam.io/abc', 'source': 'reddit'}, False),
    ({'title': 'Huge Bundle: pay $5 for 40 games', 'summary': 'Charity bundle, pay what you want starting from $5 for 40 games.', 'link': 'https://example.com/bundle', 'source': 'reddit'}, False),
]
FACTS = {'title': "Sorry We're Closed", 'summary': "Epic Games Store: бесплатная раздача игры Sorry We're Closed. Обычная цена 459₴. Бесплатно до 2026-11-05.",
         'link': 'https://store.epicgames.com/p/sorry-were-closed', 'expires_at': '2026-11-05', 'category': 'games', 'source': 'epic-games'}
GOOD = {'title': mk("Sorry We're Closed безкоштовно", "Sorry We're Closed бесплатно", "Sorry We're Closed is free", "Sorry We're Closed zadarmo"),
        'text': mk('Забирай безкоштовно в Epic Games Store до 05/11/2026. Зазвичай 459₴ 🎮', 'Забирай бесплатно в Epic Games Store до 05/11/2026. Обычно 459₴ 🎮',
                   'Free on Epic Games Store until 05/11/2026. Usually 459₴ 🎮', 'Zadarmo v Epic Games Store do 05/11/2026. Zvyčajne 459₴ 🎮')}
BAD1 = {'title': GOOD['title'], 'text': mk('Забирай безкоштовно в Epic Games Store до 15/11/2026. Зазвичай 999₴ 🎮', 'Забирай бесплатно в Epic Games Store до 15/11/2026. Обычно 999₴ 🎮',
                                         'Free on Epic Games Store until 15/11/2026. Usually 999₴ 🎮', 'Zadarmo v Epic Games Store do 15/11/2026. Zvyčajne 999₴ 🎮')}
BAD2 = {'title': GOOD['title'], 'text': mk('Назавжди безкоштовно для студентів з ISIC, потрібен промокод STUDENT 🎮', 'Навсегда бесплатно для студентов с ISIC, нужен промокод STUDENT 🎮',
                                         'Free forever for ISIC students, promo code STUDENT required 🎮', 'Navždy zadarmo pre študentov s ISIC, potrebný kód STUDENT 🎮')}

def qa(m, post):
    r = ask_llm('qa', {'source': FACTS, 'post': post}, retries=0, models=[m])
    s = r.get('score') if isinstance(r, dict) else None
    return s if isinstance(s, (int, float)) else None

def chief(m, post, score, problems):
    r = ask_llm('chief', {'post': post, 'qa': {'score': score, 'problems': problems}, 'link': FACTS['link'], 'expires_at': '2026-11-05', 'popularity': {}, 'kind': None}, retries=0, models=[m])
    return r.get('decision') if isinstance(r, dict) else None

for role in ('scout', 'qa', 'chief'):
    print('\n== роль:', role, '==')
    for m in models_for(role):
        if role == 'scout':
            ok = 0
            for item, want in SCOUT:
                r = ask_llm('scout', {'today': today().isoformat(), 'item': item}, retries=0, models=[m])
                ok += isinstance(r, dict) and bool(r.get('relevant')) == want
            print(m, '| верных решений', ok, 'из', len(SCOUT))
        elif role == 'qa':
            g, b1, b2 = qa(m, GOOD), qa(m, BAD1), qa(m, BAD2)
            ok = None not in (g, b1, b2) and g >= 75 and g - max(b1, b2) >= 15
            print(m, '| хороший пост', g, '| неверные цена и дата', b1, '| выдуманные факты', b2, '|', 'РАЗЛИЧАЕТ' if ok else 'не различает')
        else:
            a, b = chief(m, GOOD, 92, []), chief(m, BAD2, 55, ['в посте есть факты, которых нет в источнике'])
            print(m, '| хороший ->', a, '| выдуманный ->', b, '|', 'ОК' if a == 'publish' and b not in ('publish', None) else 'проверить')
