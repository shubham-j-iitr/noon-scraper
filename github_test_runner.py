import json
import os
import re
import shutil
import types
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from config import PAGE_LOAD_TIMEOUT
from excel_exporter import ExcelExporter
from noon_scraper import NoonScraper, build_noon_search_url, extract_noon_product_urls

request = json.loads(open('data/request.json', encoding='utf-8').read())
regions = ['uae', 'ksa'] if request['region'] == 'both' else [request['region']]
all_data = []
debug_dir = Path('debug')
debug_dir.mkdir(parents=True, exist_ok=True)


def save_diagnostics(scraper, region, stage):
    prefix = debug_dir / f"noon-{stage}-{re.sub(r'[^a-z0-9_-]+', '_', region.lower())}"
    try:
        scraper.driver.save_screenshot(str(prefix.with_suffix('.png')))
    except Exception as exc:
        print(f'Could not save diagnostic screenshot: {exc}')
    try:
        prefix.with_suffix('.html').write_text(scraper.driver.page_source, encoding='utf-8')
    except Exception as exc:
        print(f'Could not save diagnostic HTML: {exc}')
    try:
        body = scraper.driver.find_element(By.TAG_NAME, 'body').text
        prefix.with_suffix('.txt').write_text(body[:30000], encoding='utf-8')
        print(f'Diagnostic title: {scraper.driver.title}')
        print(f'Diagnostic URL: {scraper.driver.current_url}')
        print(f'Diagnostic body: {body[:1500]!r}')
    except Exception as exc:
        print(f'Could not save diagnostic body: {exc}')


def patch_driver(scraper):
    def init_driver(self):
        options = webdriver.ChromeOptions()
        chrome_bin = os.getenv('CHROME_BIN', '').strip()
        if chrome_bin and os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
        else:
            for candidate in (
                '/opt/hostedtoolcache/setup-chrome/chrome/stable/x64/chrome',
                '/opt/hostedtoolcache/setup-chrome/chromium/stable/x64/chrome',
                '/usr/bin/google-chrome',
            ):
                if os.path.exists(candidate):
                    options.binary_location = candidate
                    break

        options.page_load_strategy = 'eager'
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-http2')
        options.add_argument('--disable-quic')
        options.add_argument('--lang=en-US')
        options.add_argument('--accept-lang=en-US,en;q=0.9')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')

        driver_path = os.getenv('CHROMEDRIVER_PATH', '').strip()
        if driver_path and os.path.exists(driver_path):
            self.driver = webdriver.Chrome(service=Service(driver_path), options=options)
        else:
            self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(min(PAGE_LOAD_TIMEOUT, 15))
        print(f'Chrome binary: {options.binary_location}')
        print('Chrome network mode: HTTP/1.1 (--disable-http2, --disable-quic)')

    scraper._init_driver = types.MethodType(init_driver, scraper)


def patch_search(scraper, max_products):
    target = max_products or 1

    def collect(self):
        hrefs = []
        for link in self.driver.find_elements(By.CSS_SELECTOR, 'a[href]'):
            try:
                href = link.get_attribute('href')
                if href:
                    hrefs.append(href)
            except Exception:
                pass
        try:
            for node in self.driver.find_elements(By.CSS_SELECTOR, '[data-qa="product-name"]'):
                links = node.find_elements(By.XPATH, './ancestor::a[1]')
                if links:
                    href = links[0].get_attribute('href')
                    if href:
                        hrefs.append(href)
        except Exception:
            pass
        for selector in ('a[id^="productBox-"]', 'a[href*="/p/"]', 'a[href*="/product/"]'):
            try:
                for link in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    href = link.get_attribute('href')
                    if href:
                        hrefs.append(href)
            except Exception:
                pass
        return extract_noon_product_urls(hrefs)

    def wait_for_results(self):
        def signal(driver):
            try:
                return bool(collect(self)) or bool(driver.find_elements(By.CSS_SELECTOR, '[data-qa="product-name"]'))
            except Exception:
                return False
        try:
            WebDriverWait(self.driver, 20).until(signal)
            print('Noon product-result DOM signal detected.')
        except Exception:
            print('No product-result signal after 20 seconds; continuing.')

    def scroll_and_collect(self):
        urls, seen = [], set()
        for i in range(1, 16):
            for url in collect(self):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
            print(f'Search scan {i}/15: {len(urls)} unique product URLs')
            if len(urls) >= target:
                return urls[:target]
            self.driver.execute_script('window.scrollBy(0, Math.max(600, window.innerHeight * 0.85));')
            self._random_delay(1.0, 2.0)
        return urls[:target]

    def search(self, keyword):
        url = build_noon_search_url(keyword, self.region)
        print(f'Opening Noon search URL directly: {url}')
        try:
            self.driver.get(url)
        except TimeoutException as exc:
            print(f'Noon navigation timed out, inspecting the partially loaded page: {exc}')
        self._random_delay(4.0, 6.0)
        if self._detect_captcha():
            save_diagnostics(self, self.region, 'challenge')
            self.last_search_urls = []
            return False
        self.wait_for_results()
        self.last_search_urls = self.scroll_and_collect()
        print(f'FINAL SEARCH RESULT COUNT: {len(self.last_search_urls)}')
        if not self.last_search_urls:
            save_diagnostics(self, self.region, 'empty')
            return False
        print(f'FIRST PRODUCT URL: {self.last_search_urls[0]}')
        return True

    scraper.search_keyword = types.MethodType(search, scraper)
    scraper._collect_search_page_product_urls = types.MethodType(collect, scraper)
    scraper._scroll_and_collect_search_results = types.MethodType(scroll_and_collect, scraper)
    scraper.wait_for_results = types.MethodType(wait_for_results, scraper)
    scraper.scroll_and_collect = types.MethodType(scroll_and_collect, scraper)


def patch_product_details(scraper):
    original = scraper.scrape_product_details

    def details(self, product_url, keyword):
        rows = original(product_url, keyword)
        title = ''
        price = ''
        for selector in ('[data-qa="product-name"]', 'h1'):
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and elements[0].text.strip():
                    title = elements[0].text.strip()
                    break
            except Exception:
                pass
        for selector in ('strong.amount', '[class*="priceNowText"]', '[class*="priceNow"]'):
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and elements[0].text.strip():
                    value = elements[0].text.strip()
                    currency = 'SAR' if self.region == 'ksa' else 'AED'
                    price = value if currency in value else f'{currency} {value}'
                    break
            except Exception:
                pass
        for row in rows or []:
            if title and row.get('Title') in ('', 'N/A'):
                row['Title'] = title
            if price and row.get('Price') in ('', 'N/A'):
                row['Price'] = price
        return rows

    scraper.scrape_product_details = types.MethodType(details, scraper)


for region in regions:
    scraper = NoonScraper(headless=True, region=region)
    try:
        patch_driver(scraper)
        patch_search(scraper, request['max_products'])
        patch_product_details(scraper)
        all_data.extend(scraper.scrape(request['keywords'], request['max_products']))
    finally:
        scraper.close()

real_rows = [
    row for row in all_data
    if row.get('Product URL', '').startswith('https://www.noon.com/')
    and row.get('Title') not in ('', 'N/A', 'No products found for this keyword')
    and row.get('Price') not in ('', 'N/A')
]

if not real_rows:
    raise SystemExit('TEST FAILED: no real Noon product row with title, price and product URL was received')

path = ExcelExporter().export_to_excel(real_rows)
shutil.copy2(path, 'output/result.xlsx')
print(f'TEST PASSED: received {len(real_rows)} real Noon product row(s).')
for row in real_rows[:request['max_products'] or 1]:
    print(f"PRODUCT: {row.get('Title')} | PRICE: {row.get('Price')} | URL: {row.get('Product URL')}")
