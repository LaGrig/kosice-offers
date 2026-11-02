import json, re

def dedupe(t):
    t = (t or '').strip()
    m = re.match(r'^(.{30,}?)\1(.*)$', t, re.S)
    return (m.group(1) + m.group(2)).strip() if m else t

def nums(s):
    s = re.sub(r'(?<=\d)[ \u00a0\u202f,.](?=\d{3}(?!\d))', '', s)
    s = re.sub(r'(?<=\d)[.,]\d{1,2}(?!\d)', '', s)
    return {int(x) for x in re.findall(r'\d+', s)}

def clean_post(post, facts):
    if not isinstance(post, dict) or not isinstance(post.get('text'), dict) or not isinstance(post.get('title'), dict):
        return post, []
    for k in ('title', 'text'):
        for lang in list(post[k]):
            post[k][lang] = dedupe(post[k][lang])
    allowed = nums(json.dumps(facts, ensure_ascii=False))
    bad = set()
    for k in ('title', 'text'):
        for v in post[k].values():
            bad |= nums(str(v)) - allowed
    return post, sorted(bad)
