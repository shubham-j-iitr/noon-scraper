import json
import os
import re
import shutil
from pathlib import Path

from excel_exporter import ExcelExporter
from noon_scraper import NoonScraper

request = json.loads(open('data/request.json', encoding='utf-8').read())
regions = ['uae', 'ksa'] if request['region'] == 'both' else [request['region']]
all_data = []

debug_dir = Path('debug')
debug_dir.mkdir(parents=True, exist_ok=True)

for region in regions:
    scraper = NoonScraper(headless=True, region=region)
    try:
        all_data.extend(scraper.scrape(request['keywords'], request['max_products']))

        # When search returns no product URLs, preserve the actual browser
        # state so GitHub Actions failures can be diagnosed instead of being
        # reported as a misleading successful placeholder scrape.
        if not scraper.last_search_urls and scraper.driver:
            safe_region = re.sub(r'[^a-z0-9_-]+', '_', region.lower())
            try:
                scraper.driver.save_screenshot(str(debug_dir / f'noon-search-{safe_region}.png'))
            except Exception as exc:
                print(f'Could not save diagnostic screenshot: {exc}')
            try:
                (debug_dir / f'noon-search-{safe_region}.html').write_text(
                    scraper.driver.page_source,
                    encoding='utf-8',
                )
            except Exception as exc:
                print(f'Could not save diagnostic HTML: {exc}')
            try:
                body_text = scraper.driver.find_element('tag name', 'body').text
                (debug_dir / f'noon-search-{safe_region}.txt').write_text(
                    body_text[:20000],
                    encoding='utf-8',
                )
                print(f'Diagnostic page title: {scraper.driver.title}')
                print(f'Diagnostic page URL: {scraper.driver.current_url}')
                print(f'Diagnostic body excerpt: {body_text[:1000]!r}')
            except Exception as exc:
                print(f'Could not save diagnostic body text: {exc}')
    finally:
        scraper.close()

if not all_data:
    raise SystemExit('No results found')

path = ExcelExporter().export_to_excel(all_data)
shutil.copy2(path, 'output/result.xlsx')
print(f'Rows: {len(all_data)}')
