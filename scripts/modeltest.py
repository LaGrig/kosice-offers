import sys
sys.path.insert(0, 'scripts')
from common import load_offers
from llm import ask_llm
from textfix import clean_post

CAND = ['google/gemma-4-31b-it:free', 'google/gemma-4-26b-a4b-it:free', 'thinkingmachines/inkling-small:free', 'nvidia/nemotron-3.5-lightning:free', 'nvidia/nemotron-3-ultra-550b-a55b:free']
cands = sys.argv[1:] or CAND
offers = load_offers()
pick = [o for o in offers if o.get('kind') == 'deal'][:2] + [o for o in offers if o.get('kind') != 'deal'][:1]
facts = [{'title': o['title']['en'], 'summary': o['text']['en'], 'expires_at': o.get('expires_at'), 'kind': o.get('kind'),
          'category': o['category'], 'chart_rank': o.get('chart_rank')} for o in pick]
for m in cands:
    ok = langs = nums = longest = 0
    samples = []
    for f in facts:
        post = ask_llm('writer', {'facts': f}, retries=0, models=[m])
        if not isinstance(post, dict) or not isinstance(post.get('text'), dict) or not isinstance(post.get('title'), dict):
            continue
        ok += 1
        post, bad = clean_post(post, f)
        if all(post['text'].get(l) and post['title'].get(l) for l in ('uk', 'ru', 'en', 'sk')):
            langs += 1
        if not bad:
            nums += 1
        longest = max([longest] + [len(str(v)) for v in post['text'].values()])
        samples.append((post['text'].get('uk', ''), post['text'].get('sk', '')))
    print('\n' + m, '| ответов', str(ok) + '/' + str(len(facts)), '| 4 языка', langs, '| числа ок', nums, '| макс. длина', longest)
    if samples:
        print('  uk:', samples[0][0][:230])
        print('  sk:', samples[0][1][:230])
