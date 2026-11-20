import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import requests
import yaml

from common import CFG, ROOT, load_offers, offer_id, today, update_offers
from llm import ask_llm
from verify import UA, _host_matches, link_ok

DISCOVERY_CFG = ROOT / 'discovery.yaml'
STATE_FILE = ROOT / 'data' / 'discovered_urls.json'
SKIP_EXT = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.doc', '.docx', '.xls', '.xlsx', '.zip')

DISCOVER_EVAL_SYS = (
    'Ты — строгий редактор студенческого справочника выгод в Кошице (Словакия). '
    'Тебе дают целевую рубрику, URL и реальный текст, извлечённый с этой веб-страницы, а также сегодняшнюю дату.\n'
    'Определи, стоит ли добавлять эту страницу в каталог для студентов Кошице.\n'
    'Критерии ПРИНЯТИЯ (accept=true, score>=75):\n'
    '1. Это официальный сайт заведения, столовой (menza/jedáleň), сервиса или сети в Кошице (либо общесловацкая/онлайн акция, работающая в Кошице), НЕ агрегатор и НЕ новостная статья.\n'
    '2. Прямо на ЭТОЙ странице видны конкретные цены, размер скидки, дотация или понятные условия выгоды для студента (например: студенческая столовая с указанными ценами блюд/дотацией, комбо-наборы со сниженной ценой, конкретная скидка %, акция 2+1 или подарок к заказу).\n'
    '3. Для еды (food): дотированные университетские столовые Кошице (TUKE, UPJŠ, UVLF/Gastromila) с ценами или меню тоже релевантны, даже без знака «%» — это ключевая бюджетная еда студентов.\n'
    'Критерии ОТКЛОНЕНИЯ (accept=false):\n'
    '- На самой странице нет ни цен, ни скидки, ни описания студенческой выгоды (просто главная страница, контакты или форма).\n'
    '- Новость о событии в прошлом, вакансия, статья-подборка или агрегатор.\n'
    '- Предложение не работает в Кошице.\n'
    'Отвечай ТОЛЬКО JSON: {"accept": true|false, "score": 0-100, "expires_at": "YYYY-MM-DD"|null, "reason": "одна короткая фраза"}'
)

DISCOVER_WRITE_SYS = (
    'Ты — друг-старшекурсник из Кошице, который коротко, легко и по-дружески на «ты» подсказывает студенту, где выгодно поесть или сэкономить.\n'
    'Сделай карточку на 4 языках: uk, ru, en, sk (строго по фактам со страницы, ничего не выдумывая).\n'
    'Формула дружеской подсказки (читается за 3 секунды):\n'
    '- Заголовок до 70 символов: «[Оригинальное название заведения/бренда] — [главная выгода в 2–4 словах]» (например: «Študentské jedálne UPJŠ — обеды со скидкой за 4,60 €», «Jedálne TUKE — горячие обеды от 3,40 €»). Не переводи название бренда. Запрещены скучные подзаголовки вроде «: цены на питание», «: информация», «: скидки».\n'
    '- Текст — ровно 2 коротких предложения на «ты» (до 180–220 символов, один абзац без переносов строки):\n'
    '  1) Первая фраза (крючок + главная выгода): что именно получаешь и сколько экономишь. Оставь максимум 1–2 самые показательные цены во всём тексте! Не превращай текст в прайс-лист, не расписывай математику дотаций и все пороги цен.\n'
    '  2) Вторая фраза (как забрать): одно простое действие (заказывай заранее, покажи ISIC на кассе, смотри меню на день по ссылке и заходи в ближайшую столовую).\n'
    '- ЗАПРЕЩЕНЫ канцеляризмы и сложные обороты: «составляет», «предоставляется», «с учётом дотации», «при свободной продаже», «для студентов и докторантов», «спеццены», «тарифы», «в размере», «доступно питание».\n'
    '- ВСЁ описательное содержимое переводи на целевой язык (uk, ru, en, sk), сохраняя в оригинале только названия брендов, улицы/адреса и фирменные названия.\n'
    '- Начинай заголовок и текст в каждом языке с заглавной буквы (кроме брендов со строчной, например pizzaBurger). Не вставляй ссылки.\n'
    'Отвечай ТОЛЬКО JSON: {"title": {"uk": "", "ru": "", "en": "", "sk": ""}, "text": {"uk": "", "ru": "", "en": "", "sk": ""}}'
)


def root_domain(url):
    """Return normalized registered domain (e.g. tuke.sk, pizzaburgerkosice.sk)."""
    host = urlparse(url).netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    parts = host.split('.')
    if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'gov', 'edu', 'ac'):
        return '.'.join(parts[-3:])
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return host


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def _search_serper(query, num=8):
    key = os.environ.get('SERPER_API_KEY')
    if not key:
        return []
    r = requests.post(
        'https://google.serper.dev/search',
        headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
        json={'q': query, 'gl': 'sk', 'hl': 'sk', 'num': num},
        timeout=20,
    )
    r.raise_for_status()
    return [
        {'url': it['link'], 'title': it.get('title', ''), 'snippet': it.get('snippet', ''), 'via': 'serper'}
        for it in (r.json().get('organic') or [])
        if it.get('link')
    ]


def _search_tavily(query, num=8):
    key = os.environ.get('TAVILY_API_KEY')
    if not key:
        return []
    r = requests.post(
        'https://api.tavily.com/search',
        json={'api_key': key, 'query': query, 'max_results': num},
        timeout=25,
    )
    r.raise_for_status()
    return [
        {'url': it['url'], 'title': it.get('title', ''), 'snippet': it.get('content', ''), 'via': 'tavily'}
        for it in (r.json().get('results') or [])
        if it.get('url')
    ]


def web_search(query, use_tavily=False):
    if not use_tavily:
        try:
            res = _search_serper(query)
            if res:
                return res
        except Exception as e:
            print('Serper ошибка, пробую Tavily:', str(e)[:100])
    try:
        return _search_tavily(query)
    except Exception as e:
        print('Tavily ошибка:', str(e)[:100])
        return []


def _tavily_extract(url):
    key = os.environ.get('TAVILY_API_KEY')
    if not key:
        return ''
    try:
        r = requests.post('https://api.tavily.com/extract', json={'api_key': key, 'urls': [url]}, timeout=25)
        if r.status_code == 200:
            results = r.json().get('results') or []
            if results:
                return (results[0].get('raw_content') or '')[:5000]
    except Exception:
        pass
    return ''


def fetch_page_text(url):
    """Fetch visible page text (stripping nav/footer/scripts), falling back to Tavily Extract."""
    final_url = url
    txt = ''
    try:
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True)
        final_url = r.url or url
        if r.status_code < 400 and 'text/html' in (r.headers.get('content-type') or 'text/html'):
            body = re.sub(r'<(script|style|noscript|nav|footer)[^>]*>.*?</\1>', ' ', r.text, flags=re.S | re.I)
            txt = ' '.join(re.sub(r'<[^>]+>', ' ', body).split())
            if len(txt) < 250:
                body2 = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', r.text, flags=re.S | re.I)
                txt = ' '.join(re.sub(r'<[^>]+>', ' ', body2).split())
    except Exception:
        pass
    if len(txt) < 250:
        ext = _tavily_extract(final_url)
        if len(ext) > len(txt):
            txt = ' '.join(ext.split())
    return final_url, txt[:5000]


def _candidate_priority(item):
    """Prefer live canonical menu/pricing URLs and demote archived date-slug URLs."""
    u = item['url'].lower()
    score = 0
    for kw in ('jedaln', 'jedalny-listok', 'denne-menu', 'strav', 'cena', 'akci', 'zlav', 'isic', 'student', 'menu', 'gastromila'):
        if kw in u:
            score += 1
    if re.search(r'/202\d-\d{2}-\d{2}', u):
        score -= 10
    return (-score, len(u))


def discover_category(cat, activate=False, recheck=False, use_tavily=False):
    cfg = yaml.safe_load(DISCOVERY_CFG.read_text(encoding='utf-8'))
    blocked = tuple(cfg.get('blocked_domains') or [])
    cat_cfg = (cfg.get('categories') or {}).get(cat)
    if not cat_cfg:
        raise ValueError(f'Unknown discovery category: {cat}')

    existing = load_offers()
    have_links = {o['link'].rstrip('/') for o in existing}
    one_per_dom = bool(cat_cfg.get('one_per_domain', True))
    have_domains = {root_domain(o['link']) for o in existing if o.get('category') == cat} if one_per_dom else set()
    state = load_state()

    raw_candidates = []
    seen_urls = set()
    for q in cat_cfg.get('queries') or []:
        print(f'🔍 [{cat}] {q}')
        for res in web_search(q, use_tavily=use_tavily):
            u = res['url']
            ul = u.lower().split('?', 1)[0]
            if u in seen_urls or ul.endswith(SKIP_EXT) or re.search(r'/202[0-5]-\d{2}-\d{2}', ul):
                continue
            if _host_matches(u, blocked):
                continue
            seen_urls.add(u)
            raw_candidates.append(res)

    raw_candidates.sort(key=_candidate_priority)

    added = []
    max_add = int(cat_cfg.get('max_add', 8))
    today_s = today().isoformat()

    for res in raw_candidates:
        if len(added) >= max_add:
            break
        u = res['url']
        dom = root_domain(u)
        if one_per_dom and dom in have_domains:
            print(f'  skip domain {dom}: {u}')
            continue
        if u.rstrip('/') in have_links:
            continue
        if not recheck and u in state:
            print(f"  cached ({state[u]['status']}): {u}")
            continue

        final_url, txt = fetch_page_text(u)
        if _host_matches(final_url, blocked):
            state[u] = {'ts': today_s, 'status': 'skip', 'why': 'redirected to blocked domain'}
            continue
        final_dom = root_domain(final_url)
        if one_per_dom and final_dom in have_domains:
            print(f'  skip final domain {final_dom}: {final_url}')
            continue
        if final_url.rstrip('/') in have_links:
            continue
        if len(txt) < 120:
            print(f'  skip empty ({len(txt)} chars): {final_url}')
            state[u] = {'ts': today_s, 'status': 'skip', 'why': 'empty page'}
            continue
        if not link_ok(final_url):
            print(f'  skip link_ok=False: {final_url}')
            state[u] = {'ts': today_s, 'status': 'skip', 'why': 'link_ok failed'}
            continue

        ev = ask_llm('scout', {
            'today': today_s,
            'target_category': cat,
            'url': final_url,
            'search_title': res.get('title', ''),
            'page_text': txt[:4500],
        }, retries=1, system=DISCOVER_EVAL_SYS)

        if not ev or not ev.get('accept') or int(ev.get('score') or 0) < 75:
            why = (ev or {}).get('reason') or 'rejected by evaluator'
            print(f"  ❌ reject ({(ev or {}).get('score', 0)}): {final_url} -> {why}")
            state[u] = {'ts': today_s, 'status': 'skip', 'why': str(why)[:160]}
            continue

        exp = ev.get('expires_at')
        if exp and exp < today_s:
            print(f'  ❌ expired ({exp}): {final_url}')
            state[u] = {'ts': today_s, 'status': 'skip', 'why': 'expired'}
            continue

        post = ask_llm('writer', {
            'today': today_s,
            'category': cat,
            'url': final_url,
            'expires_at': exp,
            'page_text': txt[:4500],
        }, retries=1, system=DISCOVER_WRITE_SYS)

        if not post or not isinstance(post.get('title'), dict) or not isinstance(post.get('text'), dict):
            print(f'  ⚠️ writer failed: {final_url}')
            continue
        if not all((post['title'].get(l) and post['text'].get(l)) for l in ('uk', 'ru', 'en', 'sk')):
            print(f'  ⚠️ incomplete 4-lang post: {final_url}')
            continue

        oid = offer_id(final_url)
        offer = {
            'id': oid,
            'title': {l: str(post['title'][l]).strip()[:100] for l in ('uk', 'ru', 'en', 'sk')},
            'text': {l: (lambda s: (s[:1].upper() + s[1:]) if s else s)(' '.join(str(post['text'][l]).split())[:350]) for l in ('uk', 'ru', 'en', 'sk')},
            'category': cat,
            'link': final_url,
            'source': 'discovery',
            'found_at': today_s,
            'expires_at': exp,
            'score': int(ev['score']),
            'status': 'active' if activate else 'pending',
        }
        if activate:
            offer['approved_at'] = today_s
        added.append(offer)
        have_links.add(final_url.rstrip('/'))
        if one_per_dom:
            have_domains.add(final_dom)
            have_domains.add(dom)
        state[u] = {'ts': today_s, 'status': 'ok', 'why': ev.get('reason', '')[:160]}
        print(f"  ✅ ACCEPT ({offer['score']}) exp={exp}: {offer['title']['ru']} | {final_url}")

    save_state(state)
    if added:
        def merge(cur):
            have_ids = {o['id'] for o in cur}
            cur_doms = {root_domain(o['link']) for o in cur if o.get('category') == cat} if one_per_dom else set()
            for o in added:
                if o['id'] in have_ids:
                    continue
                if one_per_dom and root_domain(o['link']) in cur_doms:
                    continue
                cur.append(o)
                have_ids.add(o['id'])
                cur_doms.add(root_domain(o['link']))
        update_offers(merge)
    print(f'Итого добавлено в {cat}: {len(added)}')
    return added


if __name__ == '__main__':
    cat = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else 'food'
    discover_category(
        cat,
        activate='--activate' in sys.argv,
        recheck='--recheck' in sys.argv,
        use_tavily='--tavily' in sys.argv,
    )
