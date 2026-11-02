import json, re, time
from common import ROOT, CFG
from steam_signal import steam_signal, get_json
from dealrules import deal_quality_ok

CACHE = ROOT / 'data' / 'deal_cache.json'
EDITION = r'\b(standard|definitive|digital|deluxe|complete|ultimate|gold|premium|goty|game of the year|remastered|special|collector.?s)\s+(edition|version)\b'

def base_title(t):
    t = re.sub(r'\([^)]*\)|[™®©]', ' ', t)
    t = re.sub(EDITION, ' ', t, flags=re.I)
    return ' '.join(t.split()).strip(' -–:')

def price(it):
    return it['worth'] - it['saved']

def regional(app, cc):
    if not app:
        return None
    try:
        r = get_json('https://store.steampowered.com/api/appdetails', {'appids': app, 'cc': cc, 'filters': 'price_overview'})
        d = r.get(str(app)) or {}
        data = d.get('data')
        return data.get('price_overview') if isinstance(data, dict) else None
    except Exception:
        return None

def select_deals(items, lookups=25):
    cache = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    best = {}
    for it in items:
        k = base_title(it['title']).lower() + '|' + it['store']
        if k not in best or (it.get('chart_rank') and not best[k].get('chart_rank')) or (bool(it.get('chart_rank')) == bool(best[k].get('chart_rank')) and price(it) < price(best[k])):
            best[k] = it
    left = lookups
    for k, it in sorted(best.items(), key=lambda kv: -kv[1]['saved']):
        if it['steam_reviews'] or it['metacritic']:
            continue
        if k not in cache:
            if left <= 0:
                continue
            left -= 1
            s = steam_signal(base_title(it['title']))
            time.sleep(1)
            if 'steam_error' in s:
                continue
            cache[k] = s
        s = cache.get(k) or {}
        if s.get('steam_reviews'):
            it['steam_reviews'] = s['steam_reviews']
            it['steam_pct'] = s.get('steam_pct', 0)
            it['summary'] += ' Оценки Steam: ' + str(it['steam_pct']) + '% положительных из ' + str(it['steam_reviews']) + ' отзывов.'
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    good = [it for it in best.values() if deal_quality_ok(it)]
    good.sort(key=lambda it: (0 if it.get('chart_rank') else 1, it.get('chart_rank') or 0, -(it['steam_reviews'] or 0), -it['saved']))
    c = CFG.get('deals', {})
    limit = c.get('max_per_run', 6)
    country = {'ua': 'Украине', 'sk': 'Словакии'}.get(c.get('region', 'sk'), 'вашем регионе')
    res = []
    for it in good:
        if len(res) >= limit:
            break
        if it['store'] == 'Steam' and not it.get('chart_rank'):
            po = regional(it.get('steam_app'), c.get('region', 'sk'))
            time.sleep(1)
            if not po:
                continue
            init, fin, dp = po.get('initial', 0) / 100, po.get('final', 0) / 100, po.get('discount_percent', 0)
            if dp < c.get('min_savings', 70) or init < c.get('min_normal_local', 22):
                continue
            it['summary'] = ('Steam: скидка ' + str(dp) + '% на игру ' + it['title'] + '. Цена в ' + country + ' была ' + po.get('initial_formatted', str(init))
                             + ', стала ' + po.get('final_formatted', str(fin)) + '. '
                             + ('Оценки Steam: ' + str(it['steam_pct']) + '% положительных из ' + str(it['steam_reviews']) + ' отзывов. ' if it['steam_reviews'] else '')
                             + ('Metacritic: ' + str(it['metacritic']) + '. ' if it['metacritic'] else '') + 'Срок окончания скидки в данных не указан.')
            it['worth'] = init
            it['saved'] = init - fin
        res.append(it)
    return res
