import json
import os
from excel_exporter import ExcelExporter
from noon_scraper import NoonScraper

request = json.loads(open('data/request.json', encoding='utf-8').read())
regions = ['uae', 'ksa'] if request['region'] == 'both' else [request['region']]
all_data = []

for region in regions:
    scraper = NoonScraper(headless=True, region=region)
    try:
        all_data.extend(scraper.scrape(request['keywords'], request['max_products']))
    finally:
        scraper.close()

if not all_data:
    raise SystemExit('No results found')

path = ExcelExporter().export_to_excel(all_data)
# Normalize the generated filename to a stable location for the publisher.
import shutil
shutil.copy2(path, 'output/result.xlsx')
print(f'Rows: {len(all_data)}')
