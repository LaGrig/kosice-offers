import sys
from common import CFG, load_offers, save_offers, today
from llm import ask_llm
from collect import collect, mark_seen
from verify import link_ok, steam_ok
from popularity import signals
from steam_signal import steam_signal, steam_strong
import api_sources
from autolog import log_auto_reject

def process(item, today_s, force=False):
    s = ask_llm('scout', {'today': today_s, 'item': item})
    if not s:
        if not force:
            return None, 'скаут не ответил'
        s = {}
    if not s.get('relevant') and not force:
        return None, 'не релевантно: ' + str(s.get('note'))
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
    sig = signals(item)
    if sig.get('is_itch'):
        sig.update(steam_signal(item['title']))
        few = sig.get('ratings') is not None and sig['ratings'] < CFG.get('itch_min_ratings', 10)
        strong = steam_strong(sig, CFG.get('steam_tiers'))
        if few and not strong and not force:
            return None, 'itch: мало оценок (' + str(int(sig['ratings'])) + ') и нет сильного рейтинга в Steam'
    pop = {k: sig[k] for k in ('rating', 'ratings', 'claimed_users', 'steam_pct', 'steam_reviews') if sig.get(k) is not None}
    post = ask_llm('writer', {'facts': facts})
    qa = chief = None
    for attempt in range(2):
        if not post:
            return None, 'писатель не ответил'
        qa = ask_llm('qa', {'source': facts, 'post': post})
        if not qa:
            return None, 'QA не ответил'
        chief = ask_llm('chief', {'post': post, 'qa': qa, 'link': item['link'], 'expires_at': exp, 'popularity': pop})
        if not chief:
            return None, 'главред не ответил'
        if chief.get('decision') == 'revise' and attempt == 0:
            post = ask_llm('writer', {'facts': facts, 'qa_problems': qa.get('problems', [])})
            continue
        break
    score = qa.get('score', 0)
    if not force and (chief.get('decision') != 'publish' or score < CFG['publish_threshold']):
        return None, 'отклонено: score=' + str(score) + ' ' + str(chief.get('reason'))
    offer = {
        'id': item['id'], 'title': post['title'], 'text': post['text'],
        'category': s.get('category', 'other'), 'link': item['link'],
        'source': item['source'], 'found_at': today_s, 'expires_at': exp,
        'score': score, 'worth': item.get('worth'), 'pop': pop,
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
    for sk in api_sources.SKIPPED:
        log_auto_reject(sk, sk['why'])
    offers = load_offers()
    for item in items:
        offer, why = process(item, today_s)
        print(item['source'], '|', item['title'][:60], '->', why)
        if offer:
            offers.append(offer)
        else:
            log_auto_reject(item, why)
    save_offers(offers)
    mark_seen([i['id'] for i in items])

if __name__ == '__main__':
    main()
