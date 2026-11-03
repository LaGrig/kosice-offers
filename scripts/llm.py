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

def models_for(role):
    m = CFG['models'][role]
    return m if isinstance(m, list) else [m]

def call(model, role, payload):
    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': soul(role)},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ],
        'temperature': 0.2,
    }
    headers = {'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']}
    r = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=body, timeout=120)
    if r.status_code != 200:
        return None, r.status_code, r.text[:160]
    j = r.json()
    if 'choices' not in j:
        return None, 'no-choices', json.dumps(j.get('error') or j, ensure_ascii=False)[:160]
    return parse(j['choices'][0]['message'].get('content')), 200, ''

def ask_llm(role, payload, retries=1, models=None):
    for model in (models or models_for(role)):
        for attempt in range(retries + 1):
            try:
                time.sleep(CFG.get('llm_pause', 4))
                out, code, err = call(model, role, payload)
                if out is not None:
                    return out
                print('LLM', role, model, code, err)
                if code == 429 and 'upstream' in str(err):
                    break
                if code == 429:
                    time.sleep(20)
                    continue
                if code in (400, 401, 402, 403, 404):
                    break
            except Exception as e:
                print('LLM error', role, model, str(e)[:120])
    return None
