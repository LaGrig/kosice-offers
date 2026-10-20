import json, os, re, time, requests
from pathlib import Path
from common import CFG

def soul(role):
    return (Path.home() / '.hermes' / 'profiles' / role / 'SOUL.md').read_text(encoding='utf-8')

def parse(txt):
    if not txt:
        raise ValueError('Empty content from LLM')
    txt = txt.strip()
    m = re.search(r'\{.*\}', txt, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(txt)

def ask_llm(role, payload, retries=2):
    body = {
        'model': CFG['models'][role],
        'messages': [
            {'role': 'system', 'content': soul(role)},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ],
        'temperature': 0.2,
    }
    headers = {'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']}
    for _ in range(retries + 1):
        try:
            time.sleep(4)
            r = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=body, timeout=120)
            if r.status_code == 200:
                msg = r.json()['choices'][0]['message']
                return parse(msg.get('content'))
            print('LLM', role, r.status_code, r.text[:200])
            if r.status_code == 429:
                time.sleep(30)
        except Exception as e:
            print('LLM error', role, e)
    return None
