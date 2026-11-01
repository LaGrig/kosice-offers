import json, os, sys, requests
sys.path.insert(0, 'scripts')
from common import CFG, load_offers

TONES = {
    'дружелюбный': 'Дружелюбный и спокойный, как старший студент, который делится находкой. Без сленга и капса, максимум один эмодзи.',
    'лёгкий': 'Лёгкий студенческий: разговорный, на «ты», короткие фразы, допустим очень мягкий сленг (находка, зайдёт), без грубости, мата и иронии над читателем. До двух эмодзи.',
    'живой': 'Живой, с лёгким юмором и самоиронией, но без давления («срочно беги», «обязательно») и без вызывающих слов. До двух эмодзи.',
}
BASE = ('Перепиши пост студенческого канала в заданном тоне. Сохрани все факты, числа, даты и названия, ничего не придумывай и не добавляй. '
        'Один абзац, до 300 символов, без ссылок и без переносов строк. Язык: ')
LANGS = {'uk': 'украинский', 'ru': 'русский', 'en': 'английский', 'sk': 'словацкий'}

args = sys.argv[1:]
lang = args[0] if args and args[0] in LANGS else 'uk'
model = args[args.index('--model') + 1] if '--model' in args else CFG['models']['writer']

def ask(system, user):
    r = requests.post('https://openrouter.ai/api/v1/chat/completions',
                      headers={'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']},
                      json={'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'temperature': 0.7},
                      timeout=120)
    if r.status_code != 200:
        return 'ошибка ' + str(r.status_code)
    return r.json()['choices'][0]['message']['content'].strip()

print('модель:', model, '| язык:', lang)
for o in [x for x in load_offers() if x['status'] == 'active'][:2]:
    facts = o['title'][lang] + '. ' + o['text'][lang]
    print('\n=== ' + o['title'][lang] + ' ===\nСейчас: ' + o['text'][lang])
    for name, tone in TONES.items():
        print('\n[' + name + ']\n' + ask(BASE + LANGS[lang] + '. Тон: ' + tone, facts))
