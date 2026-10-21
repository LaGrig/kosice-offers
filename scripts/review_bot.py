import json, os, subprocess, time, requests
from common import ROOT, load_offers, save_offers, today

API = 'https://api.telegram.org/bot' + os.environ['BOT_TOKEN']
OWNER = int(os.environ['OWNER_ID'])
REJECTS = ROOT / 'data' / 'rejects.jsonl'
REASONS = {'rw': 'слабая игра или дёшево', 're': 'неактуально', 'rd': 'повтор', 'rn': 'другое'}

def call(method, **params):
    try:
        return requests.post(API + '/' + method, json=params, timeout=70).json()
    except Exception as e:
        print('ошибка', method, e)
        return {}

def push():
    subprocess.run('cd ' + str(ROOT) + ' && git add docs && git commit -qm review ; git push -q', shell=True)

def log_reject(o, reason):
    rec = {'date': today().isoformat(), 'reason': reason, 'id': o['id'], 'title': o['title'].get('ru', ''),
           'source': o['source'], 'category': o['category'], 'score': o['score'], 'worth': o.get('worth'), 'link': o['link']}
    with open(REJECTS, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def main_kb(oid, link):
    return {'inline_keyboard': [
        [{'text': '✅ Публикуем', 'callback_data': 'ok:' + oid}, {'text': '❌ Отмена', 'callback_data': 'no:' + oid}],
        [{'text': '🔗 Оригинал', 'url': link}],
    ]}

def reasons_kb(oid):
    return {'inline_keyboard': [
        [{'text': '💸 Слабая/дёшево', 'callback_data': 'rw:' + oid}, {'text': '⌛ Неактуально', 'callback_data': 're:' + oid}],
        [{'text': '🔁 Повтор', 'callback_data': 'rd:' + oid}, {'text': '⏭ Другое', 'callback_data': 'rn:' + oid}],
        [{'text': '↩️ Назад', 'callback_data': 'bk:' + oid}],
    ]}

def handle(cb):
    if cb['from']['id'] != OWNER:
        call('answerCallbackQuery', callback_query_id=cb['id'], text='Нет доступа')
        return
    action, _, oid = cb['data'].partition(':')
    msg = cb['message']
    where = {'chat_id': msg['chat']['id'], 'message_id': msg['message_id']}
    items = load_offers()
    offer = next((o for o in items if o['id'] == oid), None)
    if action in ('no', 'bk') and offer:
        kb = reasons_kb(oid) if action == 'no' else main_kb(oid, offer['link'])
        call('editMessageReplyMarkup', reply_markup=kb, **where)
        call('answerCallbackQuery', callback_query_id=cb['id'])
        return
    if action == 'ok' and offer:
        offer['status'] = 'active'
        offer['approved_at'] = today().isoformat()
        save_offers(items)
        push()
        verdict = '✅ Опубликовано'
    elif action in REASONS:
        if offer:
            log_reject(offer, REASONS[action])
            save_offers([o for o in items if o['id'] != oid])
            push()
        verdict = '❌ ' + REASONS[action]
    elif not offer and action in ('ok', 'no', 'bk'):
        verdict = 'Уже удалено'
    else:
        call('answerCallbackQuery', callback_query_id=cb['id'])
        return
    call('answerCallbackQuery', callback_query_id=cb['id'], text=verdict)
    call('editMessageReplyMarkup', reply_markup={'inline_keyboard': [[{'text': verdict, 'callback_data': 'noop'}]]}, **where)

def main():
    offset = None
    print('review-bot запущен', flush=True)
    while True:
        r = call('getUpdates', offset=offset, timeout=50, allowed_updates=['callback_query', 'message'])
        for u in r.get('result', []):
            offset = u['update_id'] + 1
            if 'callback_query' in u:
                handle(u['callback_query'])
            elif u.get('message', {}).get('text', '').startswith('/start') and u['message']['from']['id'] == OWNER:
                call('sendMessage', chat_id=OWNER, text='Готов. Карточки на подтверждение приходят сюда.')
        if not r.get('ok'):
            time.sleep(5)

main()
