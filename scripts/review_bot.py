import datetime as dt
import html
import json
import os
import re
import subprocess
import time
import requests
from common import CFG, ROOT, load_offers, offers_lock, offer_id, save_offers, today
from llm import ask_llm

API = 'https://api.telegram.org/bot' + os.environ['BOT_TOKEN']
OWNER = int(os.environ['OWNER_ID'])
REJECTS = ROOT / 'data' / 'rejects.jsonl'
REMOVED = ROOT / 'data' / 'removed.jsonl'
SENT = ROOT / 'data' / 'digest_sent.json'
LINKS = ROOT / 'docs' / 'links.json'
REASONS = {'rw': 'слабая игра или дёшево', 're': 'неактуально', 'rd': 'повтор', 'rn': 'другое'}
LANGS = ('uk', 'ru', 'en', 'sk')
PAGE_SIZE = 8
CJK = re.compile(r'[\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]')

CATS = [
    ('food', '🍔 Еда'),
    ('events', '🎟 События'),
    ('places', '📍 Места'),
    ('jobs', '💼 Работа'),
    ('it_soft', '💻 IT и софт'),
    ('services', '🧾 Услуги'),
    ('study', '🎓 Учёба'),
    ('games', '🎮 Игры'),
    ('other', '✨ Другое'),
]
CAT_MAP = dict(CATS)
CAT_EMOJI = {
    'food': '🍔', 'events': '🎟', 'places': '📍', 'jobs': '💼',
    'it_soft': '💻', 'services': '🧾', 'study': '🎓', 'games': '🎮', 'other': '🔗',
}
MODES = {
    'digest': '📢 В каталог + в дайджест',
    'cat': '📂 Только в каталог',
    'pin': '📌 Закреп вверху рубрики',
}

SYS_ONE = (
    'Переведи текст на четыре языка: uk, ru, en, sk. '
    'Сохрани смысл, числа, даты, цены, ссылки и имена собственные без изменений, ничего не выдумывай и не добавляй. '
    'Ответь ТОЛЬКО JSON: {"uk": "", "ru": "", "en": "", "sk": ""}'
)
SYS_PAIR = (
    'Переведи заголовок и текст на четыре языка: uk, ru, en, sk. '
    'Сохрани смысл, числа, даты, цены, ссылки и имена собственные без изменений, ничего не выдумывай и не добавляй. '
    'Ответь ТОЛЬКО JSON: {"title": {"uk": "", "ru": "", "en": "", "sk": ""}, "text": {"uk": "", "ru": "", "en": "", "sk": ""}}'
)

STATE = None


def clear_state():
    """Reset the owner's multi-step input state."""
    global STATE
    STATE = None


def call(method, **params):
    try:
        return requests.post(API + '/' + method, json=params, timeout=70).json()
    except Exception as e:
        print('ошибка', method, e, flush=True)
        return {}


def send_msg(text, kb=None, chat_id=OWNER):
    body = {
        'chat_id': chat_id,
        'text': text[:4000],
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    if kb:
        body['reply_markup'] = kb
    return call('sendMessage', **body)


def edit_or_send(where, text, kb=None):
    """Edit message in place when possible, otherwise send a new message."""
    if where:
        body = {
            'chat_id': where['chat_id'],
            'message_id': where['message_id'],
            'text': text[:4000],
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        if kb:
            body['reply_markup'] = kb
        res = call('editMessageText', **body)
        if res.get('ok') or 'message is not modified' in str(res.get('description', '')).lower():
            return res
    return send_msg(text, kb=kb)


def push():
    subprocess.run([str(ROOT / 'run.sh'), 'publish'])


def load_links():
    if LINKS.exists():
        return json.loads(LINKS.read_text(encoding='utf-8'))
    return []


def save_links(items):
    tmp = LINKS.with_suffix('.tmp')
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, LINKS)


def mark_no_digest(oid):
    sent = set(json.loads(SENT.read_text(encoding='utf-8'))) if SENT.exists() else set()
    if oid not in sent:
        sent.add(oid)
        SENT.write_text(json.dumps(sorted(sent)), encoding='utf-8')


def log_reject(o, reason):
    rec = {
        'date': today().isoformat(), 'reason': reason, 'id': o['id'],
        'title': o['title'].get('ru', ''), 'source': o['source'], 'category': o['category'],
        'score': o['score'], 'worth': o.get('worth'), 'pop': o.get('pop'),
        'meta': o.get('meta'), 'link': o['link'],
    }
    with open(REJECTS, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def log_removed(o, why):
    rec = {
        'ts': time.strftime('%F %T'), 'id': o['id'],
        'title': o['title'].get('ru', '') or o['title'].get('uk', ''),
        'source': o.get('source', ''), 'link': o.get('link', ''), 'why': why,
    }
    with open(REMOVED, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def _valid_langs(d, src=''):
    if not isinstance(d, dict):
        return False
    allow_cjk = bool(CJK.search(src))
    for l in LANGS:
        v = d.get(l)
        if not isinstance(v, str) or not v.strip():
            return False
        if not allow_cjk and CJK.search(v):
            return False
    return True


def translate_one(val):
    """Translate a single text value to uk, ru, en, sk with safe fallback."""
    out = ask_llm('writer', {'text': val}, retries=2, system=SYS_ONE)
    if _valid_langs(out, val):
        return {l: out[l].strip() for l in LANGS}, True
    return {l: val for l in LANGS}, False


def translate_pair(title, text):
    """Translate title and description to uk, ru, en, sk with safe fallback."""
    out = ask_llm('writer', {'title': title, 'text': text}, retries=2, system=SYS_PAIR)
    if isinstance(out, dict) and _valid_langs(out.get('title'), title) and _valid_langs(out.get('text'), text):
        return (
            {
                'title': {l: out['title'][l].strip() for l in LANGS},
                'text': {l: out['text'][l].strip() for l in LANGS},
            },
            True,
        )
    tr_t, ok1 = translate_one(title)
    tr_b, ok2 = translate_one(text)
    return {'title': tr_t, 'text': tr_b}, (ok1 and ok2)


def parse_date(s):
    """Parse '-', 'DD/MM', 'DD.MM', 'DD/MM/YYYY', or 'YYYY-MM-DD' into ISO date or None."""
    s = (s or '').strip().lower()
    if s in ('-', 'нет', 'без срока', 'none', '0'):
        return None
    m = re.fullmatch(r'(\d{1,2})[./](\d{1,2})', s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = today().year
        val = dt.date(y, mo, d)
        if val < today():
            val = dt.date(y + 1, mo, d)
        return val.isoformat()
    m = re.fullmatch(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return dt.date(y, mo, d).isoformat()
    return dt.date.fromisoformat(s).isoformat()


def fmt_date(d):
    if not d:
        return '♾ без срока'
    return d[8:10] + '/' + d[5:7] + '/' + d[:4]


def fmt_short(d):
    if not d:
        return '♾'
    return d[8:10] + '/' + d[5:7]


def main_kb(oid, link):
    return {'inline_keyboard': [
        [{'text': '✅ Публикуем', 'callback_data': 'ok:' + oid},
         {'text': '✏️ Править', 'callback_data': 'ed:' + oid},
         {'text': '❌ Отмена', 'callback_data': 'no:' + oid}],
        [{'text': '🔗 Оригинал', 'url': link}],
    ]}


def reasons_kb(oid):
    return {'inline_keyboard': [
        [{'text': '💸 Слабая/дёшево', 'callback_data': 'rw:' + oid}, {'text': '⌛ Неактуально', 'callback_data': 're:' + oid}],
        [{'text': '🔁 Повтор', 'callback_data': 'rd:' + oid}, {'text': '⏭ Другое', 'callback_data': 'rn:' + oid}],
        [{'text': '↩️ Назад', 'callback_data': 'bk:' + oid}],
    ]}


def menu_view():
    offers = load_offers()
    links = load_links()
    act = sum(1 for o in offers if o.get('status') == 'active')
    pend = sum(1 for o in offers if o.get('status') == 'pending')
    hid = sum(1 for o in offers if o.get('status') == 'hidden')
    text = (
        '⚙️ <b>Админка StudHub Košice</b>\n'
        f'🟢 Активных: <b>{act}</b> · 🟡 Ждут: <b>{pend}</b> · 🙈 Скрытых: <b>{hid}</b> · 📌 Закрепов: <b>{len(links)}</b>\n\n'
        'Выбери действие:'
    )
    kb = {'inline_keyboard': [
        [{'text': '➕ Добавить пост / закреп', 'callback_data': 'add'}],
        [{'text': f'📋 Активные ({act})', 'callback_data': 'ls:active:0'},
         {'text': f'🟡 Ждут ({pend})', 'callback_data': 'ls:pending:0'}],
        [{'text': f'🙈 Скрытые ({hid})', 'callback_data': 'ls:hidden:0'},
         {'text': f'📌 Закрепы ({len(links)})', 'callback_data': 'pins'}],
    ]}
    return text, kb


def active_cats_view():
    """Show category filter buttons (and 'All') before listing active offers."""
    counts = {}
    total = 0
    for o in load_offers():
        if o.get('status') == 'active':
            total += 1
            k = o.get('category') or 'other'
            counts[k] = counts.get(k, 0) + 1
    rows = [[{'text': f'📋 Все вместе ({total})', 'callback_data': 'ls:active:0:all'}]]
    for i in range(0, len(CATS), 3):
        rows.append([{'text': f'{lbl} ({counts.get(k, 0)})', 'callback_data': f'ls:active:0:{k}'} for k, lbl in CATS[i:i + 3]])
    rows.append([{'text': '➕ Добавить', 'callback_data': 'add'}, {'text': '🏠 Меню', 'callback_data': 'menu'}])
    text = f'🟢 <b>Активные карточки</b> (всего: {total})\n\nВыбери рубрику или открой все вместе:'
    return text, {'inline_keyboard': rows}


def list_view(status, page=0, cat='all'):
    titles = {'active': '🟢 Активные карточки', 'pending': '🟡 На проверке', 'hidden': '🙈 Скрытые карточки'}
    lang = CFG.get('digest_lang', 'uk')
    items = sorted(
        [o for o in load_offers() if o.get('status') == status and (status != 'active' or cat == 'all' or o.get('category') == cat)],
        key=lambda o: (o.get('approved_at') or o.get('found_at') or ''),
        reverse=True,
    )
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = [[
        {'text': '🟢 Активные', 'callback_data': 'ls:active:0'},
        {'text': '🟡 Ждут', 'callback_data': 'ls:pending:0'},
        {'text': '🙈 Скрытые', 'callback_data': 'ls:hidden:0'},
    ]]
    for o in chunk:
        name = (o.get('title') or {}).get(lang) or (o.get('title') or {}).get('en') or o['id']
        em = CAT_EMOJI.get(o.get('category'), '✨')
        rows.append([{'text': f'{em} {name[:28]} · {fmt_short(o.get("expires_at"))}', 'callback_data': 'adm:' + o['id']}])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append({'text': '⬅️', 'callback_data': f'ls:{status}:{page - 1}:{cat}'})
        nav.append({'text': f'{page + 1}/{pages}', 'callback_data': 'noop'})
        if page + 1 < pages:
            nav.append({'text': '➡️', 'callback_data': f'ls:{status}:{page + 1}:{cat}'})
        rows.append(nav)
    bottom = [{'text': '🗂 Рубрики', 'callback_data': 'ls:active:0'}] if status == 'active' else []
    bottom.extend([{'text': '➕ Добавить', 'callback_data': 'add'}, {'text': '🏠 Меню', 'callback_data': 'menu'}])
    rows.append(bottom)
    if status == 'active' and cat != 'all':
        head = f"🟢 Активные · {CAT_MAP.get(cat, cat)}"
    elif status == 'active':
        head = "🟢 Активные · Все рубрики"
    else:
        head = titles.get(status, status)
    body = f'<b>{head}</b> (всего: {len(items)})'
    if not chunk:
        body += '\n\nСписок пуст.'
    return body, {'inline_keyboard': rows}


def card_view(o):
    lang = CFG.get('digest_lang', 'uk')
    st_lbl = {'active': '🟢 Активна', 'pending': '🟡 На проверке', 'hidden': '🙈 Скрыта'}.get(o.get('status'), o.get('status', '?'))
    flags = [st_lbl]
    if o.get('pinned'):
        flags.append('📌 Закреп')
    if o.get('no_digest'):
        flags.append('🚫 Без дайджеста')
    title = (o.get('title') or {}).get(lang) or (o.get('title') or {}).get('en') or ''
    desc = (o.get('blurb') or {}).get(lang) or (o.get('text') or {}).get(lang) or (o.get('text') or {}).get('en') or ''
    cat = CAT_MAP.get(o.get('category'), o.get('category', '?'))
    text = (
        f"{' · '.join(flags)}\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(desc[:900])}\n\n"
        f"📂 {cat} · 📅 {fmt_date(o.get('expires_at'))} · ⭐️ {o.get('score', '?')}\n"
        f"🔖 <code>{o['id']}</code> · {html.escape(o.get('source', ''))}\n"
        f"🔗 {html.escape(o.get('link', ''))}"
    )
    status = o.get('status', 'active')
    if status == 'pending':
        top_row = [{'text': '✅ Опубликовать', 'callback_data': 'ok:' + o['id']}, {'text': '❌ Отклонить', 'callback_data': 'no:' + o['id']}]
    elif status == 'active':
        top_row = [{'text': '🙈 Скрыть', 'callback_data': 'hd:' + o['id']}, {'text': '🗑 Удалить', 'callback_data': 'rm:' + o['id']}]
    else:
        top_row = [{'text': '👁 Показать', 'callback_data': 'sh:' + o['id']}, {'text': '🗑 Удалить', 'callback_data': 'rm:' + o['id']}]
    rows = [
        top_row,
        [{'text': '✏️ Заголовок', 'callback_data': 'et:' + o['id']}, {'text': '💬 Описание', 'callback_data': 'eb:' + o['id']}],
        [{'text': '📅 Срок', 'callback_data': 'ee:' + o['id']}, {'text': '📂 Рубрика', 'callback_data': 'ec:' + o['id']}],
    ]
    if re.match(r'^https?://', o.get('link') or ''):
        rows.append([{'text': '🔗 Открыть оригинал', 'url': o['link']}])
    back_list = f"ls:active:0:{o.get('category') or 'all'}" if status == 'active' else f'ls:{status}:0'
    rows.append([{'text': '⬅️ К списку', 'callback_data': back_list}, {'text': '🏠 Меню', 'callback_data': 'menu'}])
    return text, {'inline_keyboard': rows}


def pins_view():
    links = load_links()
    lang = CFG.get('digest_lang', 'uk')
    rows = []
    for idx, l in enumerate(links):
        title = (l.get('title') or {}).get(lang) or (l.get('title') or {}).get('en') or 'Закреп'
        em = l.get('emoji') or '🔗'
        cat = CAT_MAP.get(l.get('category'), l.get('category', ''))
        rows.append([{'text': f'{em} {title[:28]} ({cat})', 'callback_data': f'pin:{idx}'}])
    rows.append([{'text': '➕ Добавить закреп', 'callback_data': 'am:pin'}, {'text': '🏠 Меню', 'callback_data': 'menu'}])
    text = f'📌 <b>Закреплённые карточки</b> (всего: {len(links)})'
    if not links:
        text += '\n\nЗакрепов пока нет.'
    return text, {'inline_keyboard': rows}


def pin_view(idx):
    links = load_links()
    if idx < 0 or idx >= len(links):
        return '⚠️ Закреп не найден.', {'inline_keyboard': [[{'text': '⬅️ К закрепам', 'callback_data': 'pins'}, {'text': '🏠 Меню', 'callback_data': 'menu'}]]}
    l = links[idx]
    lang = CFG.get('digest_lang', 'uk')
    title = (l.get('title') or {}).get(lang) or (l.get('title') or {}).get('en') or ''
    desc = (l.get('text') or {}).get(lang) or (l.get('text') or {}).get('en') or ''
    cat = CAT_MAP.get(l.get('category'), l.get('category', ''))
    text = (
        f"📌 <b>Закреп #{idx + 1}</b> · {cat}\n"
        f"{l.get('emoji') or '🔗'} <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(desc[:900])}\n\n"
        f"🔗 {html.escape(l.get('url', ''))}"
    )
    rows = [
        [{'text': '✏️ Заголовок', 'callback_data': f'pt:{idx}'}, {'text': '💬 Описание', 'callback_data': f'pb:{idx}'}],
        [{'text': '🔗 Ссылка', 'callback_data': f'pu:{idx}'}, {'text': '🗑 Удалить', 'callback_data': f'prm:{idx}'}],
    ]
    if re.match(r'^https?://', l.get('url') or ''):
        rows.append([{'text': '🔗 Открыть', 'url': l['url']}])
    rows.append([{'text': '⬅️ К закрепам', 'callback_data': 'pins'}, {'text': '🏠 Меню', 'callback_data': 'menu'}])
    return text, {'inline_keyboard': rows}


def cat_keyboard(prefix, back_cb):
    rows = []
    for i in range(0, len(CATS), 3):
        rows.append([{'text': lbl, 'callback_data': f'{prefix}:{k}'} for k, lbl in CATS[i:i + 3]])
    rows.append([{'text': '↩️ Назад', 'callback_data': back_cb}])
    return {'inline_keyboard': rows}


def update_card(oid, updater):
    """Atomically apply updater(offer) inside offers_lock and save."""
    with offers_lock():
        items = load_offers()
        o = next((x for x in items if x['id'] == oid), None)
        if not o:
            return None
        updater(o)
        save_offers(items)
        return o


def update_pin(idx, updater):
    """Atomically apply updater(pin) inside offers_lock and save docs/links.json."""
    with offers_lock():
        links = load_links()
        if idx < 0 or idx >= len(links):
            return None
        updater(links[idx])
        save_links(links)
        return links[idx]


def show_add_preview(st, where=None):
    """Translate wizard draft and display preview with Publish / Cancel."""
    wait_msg = edit_or_send(where, '⏳ Перевожу на 4 языка (uk, ru, en, sk)...')
    wait_where = {'chat_id': OWNER, 'message_id': wait_msg['result']['message_id']} if wait_msg.get('ok') else where
    tr, ok = translate_pair(st['title'], st['text'])
    st['tr'] = tr
    st['step'] = 'add_confirm'
    mode_lbl = MODES.get(st['mode'], st['mode'])
    cat_lbl = CAT_MAP.get(st['cat'], st['cat'])
    exp_lbl = '📌 Закреп (без срока)' if st['mode'] == 'pin' else fmt_date(st.get('expires_at'))
    warn = '' if ok else '\n⚠️ <i>Автоперевод не сработал, использован исходный текст.</i>\n'
    preview = (
        f"👀 <b>Предпросмотр</b>\n"
        f"{mode_lbl} · {cat_lbl} · {exp_lbl}\n"
        f"🔗 {html.escape(st['link'])}{warn}\n"
        f"🇺🇦 <b>{html.escape(tr['title']['uk'][:120])}</b>\n{html.escape(tr['text']['uk'][:350])}\n\n"
        f"🇷🇺 <b>{html.escape(tr['title']['ru'][:120])}</b>\n{html.escape(tr['text']['ru'][:350])}\n\n"
        f"🇬🇧 <b>{html.escape(tr['title']['en'][:120])}</b>\n{html.escape(tr['text']['en'][:350])}\n\n"
        f"🇸🇰 <b>{html.escape(tr['title']['sk'][:120])}</b>\n{html.escape(tr['text']['sk'][:350])}"
    )
    kb = {'inline_keyboard': [
        [{'text': '✅ Опубликовать', 'callback_data': 'ac_ok'}, {'text': '❌ Отмена', 'callback_data': 'menu'}],
    ]}
    edit_or_send(wait_where, preview, kb)


def start_add(where=None, mode=None):
    clear_state()
    if mode:
        global STATE
        STATE = {'step': 'add_cat', 'mode': mode}
        edit_or_send(where, f'{MODES[mode]}\n\nВыбери рубрику:', cat_keyboard('ac', 'add'))
        return
    kb = {'inline_keyboard': [
        [{'text': '📢 В каталог + в дайджест', 'callback_data': 'am:digest'}],
        [{'text': '📂 Только в каталог (без дайджеста)', 'callback_data': 'am:cat'}],
        [{'text': '📌 Закрепить вверху рубрики', 'callback_data': 'am:pin'}],
        [{'text': '❌ Отмена', 'callback_data': 'menu'}],
    ]}
    edit_or_send(where, '➕ <b>Новый пост / закреп</b>\n\nКуда добавить?', kb)


def send_menu(where=None):
    clear_state()
    text, kb = menu_view()
    return edit_or_send(where, text, kb)


def send_card_admin(oid, where=None):
    clear_state()
    o = next((x for x in load_offers() if x['id'] == oid), None)
    if not o:
        edit_or_send(where, '⚠️ Карточка не найдена (возможно, уже удалена).', {'inline_keyboard': [[{'text': '🏠 Меню', 'callback_data': 'menu'}]]})
        return
    text, kb = card_view(o)
    edit_or_send(where, text, kb)


def send_pin_admin(idx, where=None):
    clear_state()
    text, kb = pin_view(idx)
    edit_or_send(where, text, kb)


def _translate_with_notice(label, text):
    """Send progress message, translate text to 4 languages, and warn on fallback."""
    wait = send_msg(f'⏳ Перевожу {label} на 4 языка...')
    wait_where = {'chat_id': OWNER, 'message_id': wait['result']['message_id']} if wait.get('ok') else None
    tr, ok = translate_one(text)
    if not ok:
        send_msg('⚠️ Автоперевод не сработал, использован исходный текст.')
    return tr, wait_where


def _apply_new_expiry(oid, new_exp, where):
    def upd(o):
        o['expires_at'] = new_exp
        if isinstance(o.get('give'), dict):
            o['give']['until'] = new_exp
    o = update_card(oid, upd)
    if not o:
        edit_or_send(where, '⚠️ Карточка не найдена.')
        return
    send_card_admin(oid, where)
    if o.get('status') == 'active':
        push()


def handle_message(msg):
    global STATE
    if msg.get('from', {}).get('id') != OWNER:
        return
    text = (msg.get('text') or '').strip()
    if not text:
        if STATE:
            send_msg('Пришли текстовое сообщение или /cancel для отмены.')
        return

    if text.startswith('/'):
        cmd, _, arg = text.partition(' ')
        cmd = cmd.split('@')[0].lower()
        arg = arg.strip()
        if cmd == '/cancel':
            clear_state()
            send_msg('❌ Действие отменено.', {'inline_keyboard': [[{'text': '🏠 Меню админки', 'callback_data': 'menu'}]]})
            return
        if cmd == '/start':
            if arg.startswith('adm_'):
                send_card_admin(arg[4:])
                return
            if arg.startswith('pin_') and arg[4:].isdigit():
                send_pin_admin(int(arg[4:]))
                return
            send_menu()
            return
        if cmd == '/admin':
            send_menu()
            return
        if cmd == '/add':
            start_add()
            return
        if cmd in ('/list', '/pending'):
            clear_state()
            t, kb = active_cats_view() if cmd == '/list' else list_view('pending', 0)
            send_msg(t, kb)
            return
        clear_state()
        send_menu()
        return

    if not STATE:
        return

    step = STATE.get('step')
    if step in ('edit_title', 'edit_desc'):
        oid = STATE['oid']
        is_desc = step == 'edit_desc'
        clear_state()
        tr, wait_where = _translate_with_notice('описание' if is_desc else 'заголовок', text)
        def upd(o):
            if is_desc:
                o['text'] = dict(tr)
                if o.get('blurb') or o.get('deal') or o.get('give'):
                    o['blurb'] = dict(tr)
            else:
                o['title'] = tr
        o = update_card(oid, upd)
        if not o:
            edit_or_send(wait_where, '⚠️ Карточка не найдена.')
            return
        t, kb = card_view(o)
        edit_or_send(wait_where, t, kb)
        if o.get('status') == 'active':
            push()
        return

    if step == 'edit_exp':
        try:
            new_exp = parse_date(text)
        except ValueError:
            send_msg('⚠️ Неверный формат даты. Пример: <code>26/11</code>, <code>2026-11-26</code> или <code>-</code> (без срока).')
            return
        oid = STATE['oid']
        clear_state()
        _apply_new_expiry(oid, new_exp, None)
        return

    if step in ('pin_title', 'pin_text'):
        idx = STATE['idx']
        field = 'title' if step == 'pin_title' else 'text'
        clear_state()
        tr, wait_where = _translate_with_notice('заголовок закрепа' if field == 'title' else 'описание закрепа', text)
        p = update_pin(idx, lambda x: x.__setitem__(field, tr))
        if not p:
            edit_or_send(wait_where, '⚠️ Закреп не найден.')
            return
        t, kb = pin_view(idx)
        edit_or_send(wait_where, t, kb)
        push()
        return

    if step == 'pin_url':
        if not re.match(r'^https?://\S+$', text):
            send_msg('⚠️ Нужна ссылка вида <code>https://...</code> (или /cancel).')
            return
        idx = STATE['idx']
        clear_state()
        p = update_pin(idx, lambda x: x.__setitem__('url', text))
        if not p:
            send_msg('⚠️ Закреп не найден.')
            return
        push()
        send_pin_admin(idx)
        return

    if step == 'add_title':
        STATE['title'] = text
        STATE['step'] = 'add_text'
        send_msg('💬 Шаг 2/4: Пришли <b>описание</b> (1–3 предложения, на любом языке):', {'inline_keyboard': [[{'text': '❌ Отмена', 'callback_data': 'menu'}]]})
        return

    if step == 'add_text':
        STATE['text'] = text
        STATE['step'] = 'add_link'
        send_msg('🔗 Шаг 3/4: Пришли <b>ссылку</b> (<code>https://...</code>):', {'inline_keyboard': [[{'text': '❌ Отмена', 'callback_data': 'menu'}]]})
        return

    if step == 'add_link':
        if not re.match(r'^https?://\S+$', text):
            send_msg('⚠️ Нужна корректная ссылка, начинающаяся с <code>http://</code> или <code>https://</code>:')
            return
        STATE['link'] = text
        if STATE['mode'] == 'pin':
            show_add_preview(STATE)
            return
        STATE['step'] = 'add_exp'
        kb = {'inline_keyboard': [
            [{'text': '+3 дн.', 'callback_data': 'ae:3'}, {'text': '+7 дн.', 'callback_data': 'ae:7'},
             {'text': '+14 дн.', 'callback_data': 'ae:14'}, {'text': '+30 дн.', 'callback_data': 'ae:30'}],
            [{'text': '♾ Без срока', 'callback_data': 'ae:none'}, {'text': '❌ Отмена', 'callback_data': 'menu'}],
        ]}
        send_msg('📅 Шаг 4/4: Введи дату окончания (<code>26/11</code> или <code>2026-11-26</code>) или выбери кнопкой:', kb)
        return

    if step == 'add_exp':
        try:
            STATE['expires_at'] = parse_date(text)
        except ValueError:
            send_msg('⚠️ Неверный формат даты. Пример: <code>26/11</code>, <code>2026-11-26</code> или <code>-</code> (без срока).')
            return
        show_add_preview(STATE)


def handle(cb):
    global STATE
    if cb['from']['id'] != OWNER:
        call('answerCallbackQuery', callback_query_id=cb['id'], text='Нет доступа')
        return
    data = cb.get('data') or ''
    if data == 'noop':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        return
    msg = cb['message']
    where = {'chat_id': msg['chat']['id'], 'message_id': msg['message_id']}
    parts = data.split(':')
    action = parts[0]
    oid = parts[1] if len(parts) > 1 else ''

    # Legacy channel delete and auto-reject rescue handlers
    if action == 'dm':
        res = call('deleteMessage', chat_id=os.environ['CHANNEL'], message_id=int(oid))
        label = '🗑 Видалено з каналу' if res.get('ok') else '⚠️ Не вдалося видалити'
        call('answerCallbackQuery', callback_query_id=cb['id'], text=label)
        call('editMessageReplyMarkup', reply_markup={'inline_keyboard': [[{'text': label, 'callback_data': 'noop'}]]}, **where)
        return
    if action == 'rs':
        call('answerCallbackQuery', callback_query_id=cb['id'], text='Запускаю редакцию, это до минуты')
        cmd = 'cd ' + str(ROOT) + ' && .venv/bin/python scripts/rescue.py ' + oid + ' && .venv/bin/python scripts/review_send.py'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        ok = 'RESCUED' in res.stdout
        lines = res.stdout.strip().splitlines()
        label = '↩️ Возвращено: карточка придёт на проверку' if ok else '⚠️ ' + (lines[-1][:50] if lines else 'ошибка')
        call('editMessageReplyMarkup', reply_markup={'inline_keyboard': [[{'text': label, 'callback_data': 'noop'}]]}, **where)
        return

    # Admin navigation & lists
    if action == 'menu':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        send_menu(where)
        return
    if action == 'ls':
        clear_state()
        call('answerCallbackQuery', callback_query_id=cb['id'])
        if oid == 'active' and len(parts) < 4:
            t, kb = active_cats_view()
        else:
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            cat = parts[3] if len(parts) > 3 else 'all'
            t, kb = list_view(oid, page, cat)
        edit_or_send(where, t, kb)
        return
    if action in ('adm', 'ed'):
        call('answerCallbackQuery', callback_query_id=cb['id'])
        send_card_admin(oid, where)
        return
    if action == 'pins':
        clear_state()
        call('answerCallbackQuery', callback_query_id=cb['id'])
        t, kb = pins_view()
        edit_or_send(where, t, kb)
        return
    if action == 'pin':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        send_pin_admin(int(oid), where)
        return

    # Add wizard callbacks
    if action == 'add':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        start_add(where)
        return
    if action == 'am':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        start_add(where, mode=oid)
        return
    if action == 'ac':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        if not STATE or 'mode' not in STATE:
            start_add(where)
            return
        STATE['cat'] = oid
        STATE['step'] = 'add_title'
        edit_or_send(
            where,
            f"{MODES[STATE['mode']]} · {CAT_MAP.get(oid, oid)}\n\n✏️ Шаг 1/4: Пришли <b>заголовок</b> (на любом языке — переведу на 4 языка):",
            {'inline_keyboard': [[{'text': '❌ Отмена', 'callback_data': 'menu'}]]},
        )
        return
    if action == 'ae':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        if not STATE or STATE.get('step') != 'add_exp':
            start_add(where)
            return
        STATE['expires_at'] = None if oid == 'none' else (today() + dt.timedelta(days=int(oid))).isoformat()
        show_add_preview(STATE, where)
        return
    if action == 'ac_ok':
        if not STATE or STATE.get('step') != 'add_confirm':
            call('answerCallbackQuery', callback_query_id=cb['id'], text='Черновик устарел')
            send_menu(where)
            return
        st = dict(STATE)
        clear_state()
        call('answerCallbackQuery', callback_query_id=cb['id'], text='⏳ Сохраняю и публикую...')
        if st['mode'] == 'pin':
            with offers_lock():
                links = load_links()
                links.append({
                    'category': st['cat'],
                    'emoji': CAT_EMOJI.get(st['cat'], '📌'),
                    'url': st['link'],
                    'title': st['tr']['title'],
                    'text': st['tr']['text'],
                })
                save_links(links)
                new_idx = len(links) - 1
            edit_or_send(
                where,
                f"✅ Закреп опубликован: <b>{html.escape(st['tr']['title']['uk'])}</b>",
                {'inline_keyboard': [[{'text': '⚙️ Открыть закреп', 'callback_data': f'pin:{new_idx}'}, {'text': '🏠 Меню', 'callback_data': 'menu'}]]},
            )
            push()
            return
        with offers_lock():
            items = load_offers()
            new_id = offer_id(st['link'] + '|' + st['title'])
            if any(x['id'] == new_id for x in items):
                new_id = offer_id(st['link'] + '|' + st['title'] + '|' + str(int(time.time())))
            card = {
                'id': new_id,
                'title': st['tr']['title'],
                'text': st['tr']['text'],
                'category': st['cat'],
                'link': st['link'],
                'source': 'manual',
                'found_at': today().isoformat(),
                'approved_at': today().isoformat(),
                'expires_at': st.get('expires_at'),
                'score': 90,
                'status': 'active',
            }
            if st['mode'] == 'cat':
                card['no_digest'] = True
                mark_no_digest(new_id)
            items.append(card)
            save_offers(items)
        edit_or_send(
            where,
            f"✅ Опубликовано в каталоге: <b>{html.escape(st['tr']['title']['uk'])}</b>",
            {'inline_keyboard': [[{'text': '⚙️ Открыть карточку', 'callback_data': 'adm:' + new_id}, {'text': '🏠 Меню', 'callback_data': 'menu'}]]},
        )
        push()
        return

    # Pin edit/delete callbacks
    if action in ('pt', 'pb', 'pu'):
        idx = int(oid)
        step_map = {'pt': ('pin_title', '✏️ Пришли новый <b>заголовок</b> закрепа:'),
                    'pb': ('pin_text', '💬 Пришли новое <b>описание</b> закрепа:'),
                    'pu': ('pin_url', '🔗 Пришли новую <b>ссылку</b> (<code>https://...</code>):')}
        clear_state()
        STATE = {'step': step_map[action][0], 'idx': idx}
        call('answerCallbackQuery', callback_query_id=cb['id'])
        send_msg(step_map[action][1] + '\n\nДля отмены: /cancel', {'inline_keyboard': [[{'text': '❌ Отмена', 'callback_data': f'pin:{idx}'}]]})
        return
    if action == 'prm':
        idx = int(oid)
        links = load_links()
        if idx < 0 or idx >= len(links):
            call('answerCallbackQuery', callback_query_id=cb['id'], text='Закреп не найден')
            return
        title = (links[idx].get('title') or {}).get('ru') or 'закреп'
        call('answerCallbackQuery', callback_query_id=cb['id'])
        edit_or_send(where, f'⚠️ Точно удалить закреп «<b>{html.escape(title)}</b>»?', {'inline_keyboard': [
            [{'text': '✅ Да, удалить', 'callback_data': f'prc:{idx}'}, {'text': '↩️ Назад', 'callback_data': f'pin:{idx}'}],
        ]})
        return
    if action == 'prc':
        idx = int(oid)
        call('answerCallbackQuery', callback_query_id=cb['id'], text='🗑 Удаляю...')
        with offers_lock():
            links = load_links()
            if idx < 0 or idx >= len(links):
                edit_or_send(where, '⚠️ Закреп не найден.', {'inline_keyboard': [[{'text': '🏠 Меню', 'callback_data': 'menu'}]]})
                return
            links.pop(idx)
            save_links(links)
        t, kb = pins_view()
        edit_or_send(where, t, kb)
        push()
        return

    # Card edit prompts
    if action in ('et', 'eb', 'ee'):
        clear_state()
        prompts = {
            'et': ('edit_title', '✏️ Пришли новый <b>заголовок</b> (на любом языке — переведу на uk/ru/en/sk):', None),
            'eb': ('edit_desc', '💬 Пришли новое <b>описание</b> (на любом языке — переведу на uk/ru/en/sk):', None),
            'ee': ('edit_exp', '📅 Пришли новую <b>дату окончания</b> (<code>26/11</code>, <code>2026-11-26</code> или <code>-</code>):',
                   [{'text': '♾ Без срока', 'callback_data': 'se:' + oid + ':none'}]),
        }
        step_name, prompt, extra = prompts[action]
        STATE = {'step': step_name, 'oid': oid}
        call('answerCallbackQuery', callback_query_id=cb['id'])
        rows = [extra] if extra else []
        rows.append([{'text': '❌ Отмена', 'callback_data': 'adm:' + oid}])
        send_msg(prompt + '\n\nДля отмены: /cancel', {'inline_keyboard': rows})
        return
    if action == 'se':
        clear_state()
        val = None if (len(parts) > 2 and parts[2] == 'none') else parts[2]
        call('answerCallbackQuery', callback_query_id=cb['id'], text='📅 Срок обновлён')
        _apply_new_expiry(oid, val, where)
        return
    if action == 'ec':
        call('answerCallbackQuery', callback_query_id=cb['id'])
        edit_or_send(where, '📂 Выбери новую рубрику:', cat_keyboard('sc:' + oid, 'adm:' + oid))
        return
    if action == 'sc':
        new_cat = parts[2]
        call('answerCallbackQuery', callback_query_id=cb['id'], text='📂 Рубрика обновлена')
        o = update_card(oid, lambda x: x.__setitem__('category', new_cat))
        if not o:
            edit_or_send(where, '⚠️ Карточка не найдена.')
            return
        send_card_admin(oid, where)
        if o.get('status') == 'active':
            push()
        return

    # Card visibility & deletion actions
    if action in ('hd', 'sh'):
        new_st = 'hidden' if action == 'hd' else 'active'
        def upd(x):
            x['status'] = new_st
            if new_st == 'active' and not x.get('approved_at'):
                x['approved_at'] = today().isoformat()
        call('answerCallbackQuery', callback_query_id=cb['id'], text='🙈 Скрыто' if new_st == 'hidden' else '👁 Показано')
        o = update_card(oid, upd)
        if not o:
            edit_or_send(where, '⚠️ Карточка не найдена.')
            return
        send_card_admin(oid, where)
        push()
        return
    if action == 'rm':
        o = next((x for x in load_offers() if x['id'] == oid), None)
        if not o:
            call('answerCallbackQuery', callback_query_id=cb['id'], text='Карточка не найдена')
            return
        title = (o.get('title') or {}).get('ru') or (o.get('title') or {}).get('uk') or oid
        call('answerCallbackQuery', callback_query_id=cb['id'])
        edit_or_send(where, f'⚠️ Точно удалить карточку «<b>{html.escape(title)}</b>»?', {'inline_keyboard': [
            [{'text': '✅ Да, удалить', 'callback_data': 'rc:' + oid}, {'text': '↩️ Назад', 'callback_data': 'adm:' + oid}],
        ]})
        return
    if action == 'rc':
        call('answerCallbackQuery', callback_query_id=cb['id'], text='🗑 Удаляю...')
        old_st, old_cat = 'active', 'all'
        with offers_lock():
            items = load_offers()
            target = next((x for x in items if x['id'] == oid), None)
            if target:
                old_st = target.get('status', 'active')
                old_cat = target.get('category') or 'all'
                log_removed(target, 'admin rm')
                save_offers([x for x in items if x['id'] != oid])
        back_list = f'ls:active:0:{old_cat}' if old_st == 'active' else f'ls:{old_st}:0'
        edit_or_send(where, '🗑 Карточка удалена.', {'inline_keyboard': [
            [{'text': '⬅️ К списку', 'callback_data': back_list}, {'text': '🏠 Меню', 'callback_data': 'menu'}],
        ]})
        if target and old_st == 'active':
            push()
        return

    # Morning review moderation callbacks (no, bk, ok, reasons)
    with offers_lock():
        items = load_offers()
        offer = next((o for o in items if o['id'] == oid), None)
        with open(ROOT / 'data' / 'decisions.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': time.strftime('%F %T'), 'action': action, 'id': oid, 'found': offer is not None}) + '\n')
        if action in ('no', 'bk') and offer:
            kb = reasons_kb(oid) if action == 'no' else main_kb(oid, offer['link'])
            call('editMessageReplyMarkup', reply_markup=kb, **where)
            call('answerCallbackQuery', callback_query_id=cb['id'])
            return
        should_push = False
        if action == 'ok' and offer:
            offer['status'] = 'active'
            offer['approved_at'] = today().isoformat()
            save_offers(items)
            verdict = '✅ Опубликовано'
            should_push = True
        elif action in REASONS:
            if offer:
                log_reject(offer, REASONS[action])
                save_offers([o for o in items if o['id'] != oid])
                should_push = True
            verdict = '❌ ' + REASONS[action]
        elif not offer and action in ('ok', 'no', 'bk'):
            verdict = 'Уже удалено'
        else:
            call('answerCallbackQuery', callback_query_id=cb['id'])
            return
    call('answerCallbackQuery', callback_query_id=cb['id'], text=verdict)
    if action == 'ok' and offer:
        call('editMessageReplyMarkup', reply_markup={'inline_keyboard': [[
            {'text': verdict, 'callback_data': 'noop'},
            {'text': '⚙️ Карточка', 'callback_data': 'adm:' + oid},
        ]]}, **where)
    else:
        call('editMessageReplyMarkup', reply_markup={'inline_keyboard': [[{'text': verdict, 'callback_data': 'noop'}]]}, **where)
    if should_push:
        push()


def register_commands():
    cmds = [
        {'command': 'admin', 'description': 'Открыть меню админки'},
        {'command': 'add', 'description': 'Добавить пост или закреп'},
        {'command': 'list', 'description': 'Список активных карточек'},
        {'command': 'pending', 'description': 'Карточки на подтверждении'},
        {'command': 'cancel', 'description': 'Отменить текущее действие'},
    ]
    try:
        r = call('setMyCommands', commands=cmds, scope={'type': 'chat', 'chat_id': OWNER})
        print('setMyCommands:', r.get('ok'), flush=True)
    except Exception as e:
        print('setMyCommands error:', e, flush=True)


def main():
    register_commands()
    offset = None
    print('review-bot запущен', flush=True)
    while True:
        r = call('getUpdates', offset=offset, timeout=50, allowed_updates=['callback_query', 'message'])
        for u in r.get('result', []):
            offset = u['update_id'] + 1
            try:
                if 'callback_query' in u:
                    handle(u['callback_query'])
                elif 'message' in u:
                    handle_message(u['message'])
            except Exception as e:
                print('ошибка обработки апдейта:', e, flush=True)
        if not r.get('ok'):
            time.sleep(5)


if __name__ == '__main__':
    main()
