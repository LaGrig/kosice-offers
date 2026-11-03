import contextlib, fcntl, json, hashlib, os, datetime as dt
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
    tmp = OFFERS.with_suffix('.tmp')
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, OFFERS)

@contextlib.contextmanager
def offers_lock():
    (ROOT / 'data').mkdir(exist_ok=True)
    with open(ROOT / 'data' / 'offers.lock', 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def update_offers(fn):
    with offers_lock():
        items = load_offers()
        res = fn(items)
        save_offers(items if res is None else res)

def offer_id(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]
