import sys
from common import CFG, load_offers, save_offers, today
from llm import ask_llm
from collect import collect, mark_seen
from verify import link_ok, steam_ok

def process(item, today_s):
    s = ask_llm('scout', {'today': today_s, 'item': item})
    if not s or not s.get('relevant'):
        return None, 'не релевантно'
    exp = item.get('expires_at') or s.get('expires_at')
    if exp and exp < today_s:
        return None, 'срок истёк'
    if not link_ok(item['link']):
        return None, 'ссылка не открывается'
    if not steam_ok(item['link'] + ' ' + item['summary']):
        return None, 'Steam: не игра или набор'
    facts = dict(item)
    for k in ('category', 'expires_at', 'free', 'note'):
        facts[k] = s.get(k)
    facts['expires_at'] = exp
    post = ask_llm('writer', {'facts': facts})
    qa = chief = None
    for attempt in range(2):
        if not post:
            return None, 'писатель не ответил'
        qa = ask_llm('qa', {'source': facts, 'post': post})
        if not qa:
            return None, 'QA не ответил'
        chief = ask_llm('chief', {'post': post, 'qa': qa})
        if not chief:
            return None, 'главред не ответил'
        if chief.get('decision') == 'revise' and attempt == 0:
            post = ask_llm('writer', {'facts': facts, 'qa_problems': qa.get('problems', [])})
            continue
        break
    score = qa.get('score', 0)
    if chief.get('decision') != 'publish' or score < CFG['publish_threshold']:
        return None, 'отклонено: score=' + str(score) + ' ' + str(chief.get('reason'))
    offer = {
        'id': item['id'], 'title': post['title'], 'text': post['text'],
        'category': s.get('category', 'other'), 'link': item['link'],
        'source': item['source'], 'found_at': today_s, 'expires_at': exp,
        'score': score,
        'status': 'active' if CFG['auto_publish'] else 'pending',
    }
    return offer, 'ok'

def main():
    limit = CFG['max_new_per_run']
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    today_s = today().isoformat()
    items = collect()[:limit]
    print('к обработке:', len(items))
    offers = load_offers()
    for item in items:
        offer, why = process(item, today_s)
        print(item['source'], '|', item['title'][:60], '->', why)
        if offer:
            offers.append(offer)
    save_offers(offers)
    mark_seen([i['id'] for i in items])

main()
