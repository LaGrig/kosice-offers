import json, hashlib, datetime as dt
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
CFG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
OFFERS = ROOT / 'docs' / 'offers.json'

def today():
    return dt.date.today()

def load_offers():
    if OFFERS.exists():
        return json.loads(OFFERS.read_text(encoding='utf-8'))
    return []

def save_offers(items):
    OFFERS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')

def offer_id(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]
