from common import CFG
from steam_signal import steam_strong

def deal_quality_ok(item):
    c = CFG.get('deals', {})
    n = item.get('steam_reviews') or 0
    pct = item.get('steam_pct') or 0
    if item.get('chart_rank'):
        if n == 0:
            return True
        return steam_strong({'steam_reviews': n, 'steam_pct': pct}, CFG.get('steam_tiers'))
    if item.get('popular'):
        return steam_strong({'steam_reviews': n, 'steam_pct': pct}, CFG.get('steam_tiers'))
    mc = item.get('metacritic') or 0
    return (n >= c.get('min_steam_reviews', 200) and pct >= c.get('min_steam_pct', 80)) or mc >= c.get('min_metacritic', 75)
