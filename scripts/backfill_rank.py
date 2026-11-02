import sys
sys.path.insert(0, 'scripts')
from common import load_offers, save_offers
from chartdeals import chart_deals
from epiccharts import epic_chart_deals

rank = {x['link']: x['chart_rank'] for x in chart_deals() + epic_chart_deals()}
items = load_offers()
n = 0
for o in items:
    if o.get('kind') == 'deal' and not o.get('chart_rank') and o['link'] in rank:
        o['chart_rank'] = rank[o['link']]
        n += 1
save_offers(items)
print('проставлено мест в рейтинге:', n, 'из', sum(1 for o in items if o.get('kind') == 'deal'))
