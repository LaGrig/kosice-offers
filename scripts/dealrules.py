from common import CFG

def deal_quality_ok(item):
    c = CFG.get('deals', {})
    n = item.get('steam_reviews') or 0
    pct = item.get('steam_pct') or 0
    mc = item.get('metacritic') or 0
    return (n >= c.get('min_steam_reviews', 200) and pct >= c.get('min_steam_pct', 80)) or mc >= c.get('min_metacritic', 75)
