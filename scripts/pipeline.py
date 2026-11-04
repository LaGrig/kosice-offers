import sys
from common import CFG, load_offers, save_offers, update_offers, today
from llm import ask_llm
from collect import collect, mark_seen
from verify import link_ok, steam_ok
from popularity import signals
from steam_signal import steam_signal, steam_strong
from textfix import clean_post
from dealrules import deal_quality_ok
from dealtext import deal_post
from blurb import make_blurb
import api_sources
from autolog import log_auto_reject

def process(item, today_s, force=False):
    if 'itch' in (item['title'] + ' ' + item['link']).lower() and (item.get('worth') or 0) < CFG.get('min_worth', {}).get('itch', 9) and not force:
        return None, 'itch: исходная цена ниже 9 или неизвестна'
    if item.get('kind') == 'deal':
        if not force and not deal_quality_ok(item):
            return None, 'скидка: нет подтверждения качества'
        if item.get('steam_app') and not force and not steam_ok('store.steampowered.com/app/' + str(item['steam_app'])):
            return None, 'Steam: не игра или набор'
        s = {'relevant': True, 'category': 'games', 'expires_at': None, 'free': False, 'note': 'скидка на AAA-игру'}
    else:
        s = ask_llm('scout', {'today': today_s, 'item': item})
    if not s:
        if not force:
            return None, 'LLM: скаут не ответил'
        s = {}
    if not s.get('relevant') and not force:
        return None, 'не релевантно: ' + str(s.get('note'))
    exp = item.get('expires_at') or s.get('expires_at')
    if exp and exp < today_s:
        return None, 'срок истёк'
    if not link_ok(item['link']):
        return None, 'ссылка не открывается'
    if item.get('kind') not in ('demo', 'playtest', 'beta') and not steam_ok(item['link'] + ' ' + item['summary']):
        return None, 'Steam: не игра или набор'
    if item.get('kind') == 'deal' and item.get('deal'):
        post = deal_post(item)
        auto = CFG['auto_publish'] or (item.get('chart_rank') and CFG.get('deals', {}).get('auto_chart'))
        return {'id': item['id'], 'title': post['title'], 'text': post['text'], 'category': 'games', 'link': item['link'],
                'source': item['source'], 'found_at': today_s, 'expires_at': None, 'score': 90, 'worth': item.get('worth'),
                'pop': {}, 'meta': None, 'kind': 'deal', 'chart_rank': item.get('chart_rank'), 'deal': item['deal'],
                'blurb': make_blurb(item['deal']['game'], item.get('desc')),
                'status': 'active' if auto else 'pending'}, 'ok'
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
    meta = sig.get('meta')
    post = ask_llm('writer', {'facts': facts})
    post, bad = clean_post(post, facts)
    if bad and not force:
        return None, 'числа не из источника: ' + ','.join(map(str, bad))
    qa = chief = None
    for attempt in range(2):
        if not post:
            return None, 'LLM: писатель не ответил'
        qa = ask_llm('qa', {'source': facts, 'post': post})
        if not qa:
            return None, 'LLM: QA не ответил'
        chief = ask_llm('chief', {'post': post, 'qa': qa, 'link': item['link'], 'expires_at': exp, 'popularity': pop, 'kind': item.get('kind')})
        if not chief:
            return None, 'LLM: главред не ответил'
        if chief.get('decision') == 'revise' and attempt == 0:
            post = ask_llm('writer', {'facts': facts, 'qa_problems': qa.get('problems', [])})
            post, _ = clean_post(post, facts)
            continue
        break
    score = qa.get('score', 0)
    if not force and (chief.get('decision') != 'publish' or score < CFG['publish_threshold']):
        return None, 'отклонено: score=' + str(score) + ' ' + str(chief.get('reason'))
    offer = {
        'id': item['id'], 'title': post['title'], 'text': post['text'],
        'category': s.get('category', 'other'), 'link': item['link'],
        'source': item['source'], 'found_at': today_s, 'expires_at': exp,
        'score': score, 'worth': item.get('worth'), 'pop': pop, 'meta': meta, 'kind': item.get('kind'), 'chart_rank': item.get('chart_rank'), 'give': item.get('give'),
        'status': 'active' if (CFG['auto_publish'] or (item.get('chart_rank') and CFG.get('deals', {}).get('auto_chart'))) else 'pending',
    }
    offer['blurb'] = make_blurb((item.get('give') or {}).get('game') or item['title'], item.get('desc'))
    return offer, 'ok'

def main():
    limit = CFG['max_new_per_run']
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    today_s = today().isoformat()
    allc = collect()
    items = [i for i in allc if i.get('kind') != 'deal'][:limit] + [i for i in allc if i.get('kind') == 'deal']
    print('к обработке:', len(items))
    for sk in api_sources.SKIPPED:
        log_auto_reject(sk, sk['why'])
    offers = load_offers()
    failed = set()
    added = []
    for item in items:
        offer, why = process(item, today_s)
        print(item['source'], '|', item['title'][:60], '->', why)
        if offer:
            offers.append(offer)
            added.append(offer)
        elif why.startswith('LLM:'):
            failed.add(item['id'])
        else:
            log_auto_reject(item, why)
    def merge(cur):
        have = {o['id'] for o in cur}
        cur.extend(o for o in added if o['id'] not in have)
    update_offers(merge)
    mark_seen([i['id'] for i in items if i['id'] not in failed])

if __name__ == '__main__':
    main()
