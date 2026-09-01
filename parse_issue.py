import json
import os
import re
import sys

body = sys.argv[1]
match = re.search(r'<!-- NOON_SCRAPE_REQUEST -->\s*```json\s*(.*?)\s*```', body, re.S)
if not match:
    raise SystemExit('Missing scrape request payload')

payload = json.loads(match.group(1))
keywords = [str(x).strip() for x in payload.get('keywords', []) if str(x).strip()]
region = str(payload.get('region', 'uae')).lower()
max_products = int(payload.get('max_products', 10))

if not 1 <= len(keywords) <= 5:
    raise SystemExit('Use 1-5 keywords')
if region not in {'uae', 'ksa', 'both'}:
    raise SystemExit('Invalid region')
if not 1 <= max_products <= 50:
    raise SystemExit('Use 1-50 products per keyword')

out = {'keywords': keywords, 'region': region, 'max_products': max_products}
os.environ['SCRAPE_REQUEST'] = json.dumps(out)
with open('data/request.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
print(f'keywords={"|".join(keywords)}')
print(f'region={region}')
print(f'max_products={max_products}')
