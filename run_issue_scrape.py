import json
import re
import shutil
import types
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from excel_exporter import ExcelExporter
from noon_scraper import NoonScraper, build_noon_search_url, extract_noon_product_urls

request = json.loads(open('data/request.json', encoding='utf-8').read())
regions = ['uae', 'ksa'] if request['region'] == 'both' else [request['region']]
all_data = []

debug_dir = Path('debug')
debug_dir.mkdir(parents=True, exist_ok=True)


def save_search_diagnostics(scraper, region, stage='search'):
    safe_region = re.sub(r'[^a-z0-9_-]+', '_', region.lower())
    prefix = debug_dir / f'noon-{stage}-{safe_region}'
    try:
        scraper.driver.save_screenshot(str(prefix.with_suffix('.png')))
    except Exception as exc:
        print(f'Could not save diagnostic screenshot: {exc}')
    try:
        prefix.with_suffix('.html').write_text(scraper.driver.page_source, encoding='utf-8')
    except Exception as exc:
        print(f'Could not save diagnostic HTML: {exc}')
    try:
        body_text = scraper.driver.find_element(By.TAG_NAME, 'body').text
        prefix.with_suffix('.txt').write_text(body_text[:30000], encoding='utf-8')
        print(f'Diagnostic page title: {scraper.driver.title}')
        print(f'Diagnostic page URL: {scraper.driver.current_url}')
        print(f'Diagnostic body excerpt: {body_text[:1500]!r}')
    except Exception as exc:
        print(f'Could not save diagnostic body text: {exc}')


def install_robust_noon_search(scraper, max_products):
    target = max_products or 1

    def collect(self):
        hrefs = []
        try:
            for link in self.driver.find_elements(By.CSS_SELECTOR, 'a[href]'):
                try:
                    href = link.get_attribute('href')
                    if href:
                        hrefs.append(href)
                except Exception:
                    continue
        except Exception:
            pass

        try:
            name_nodes = self.driver.find_elements(By.CSS_SELECTOR, '[data-qa="product-name"]')
            for node in name_nodes:
                try:
                    parent_links = node.find_elements(By.XPATH, './ancestor::a[1]')
                    if parent_links:
                        href = parent_links[0].get_attribute('href')
                        if href:
                            hrefs.append(href)
                except Exception:
                    continue
        except Exception:
            pass

        for selector in ('a[id^="productBox-"]', 'a[href*="/p/"]', 'a[href*="/product/"]'):
            try:
                for link in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    href = link.get_attribute('href')
                    if href:
                        hrefs.append(href)
            except Exception:
                continue

        return extract_noon_product_urls(hrefs)

    def wait_for_results(self):
        def has_product_signal(driver):
            try:
                if collect(self):
                    return True
                return bool(driver.find_elements(By.CSS_SELECTOR, '[data-qa="product-name"]'))
            except Exception:
                return False
        try:
            WebDriverWait(self.driver, 25).until(has_product_signal)
            print('Noon product-result DOM signal detected.')
        except Exception:
            print('No product-result DOM signal after 25 seconds; continuing diagnostic scan.')

    def scroll_and_collect(self):
        all_urls = []
        seen = set()
        unchanged_rounds = 0
        print('Using incremental scrolling to trigger Noon lazy-loaded results...')
        for scroll_num in range(1, 16):
            for url in collect(self):
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)
            if len(all_urls) >= target:
                break

            self.driver.execute_script(
                "window.scrollBy({top: Math.max(500, Math.floor(window.innerHeight * 0.85)), behavior: 'smooth'});"
            )
            self._random_delay(1.0, 2.0)

            for url in collect(self):
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)
            print(f'Search scroll {scroll_num}/15: {len(all_urls)} unique product URLs')
            if len(all_urls) >= target:
                break

            before = len(all_urls)
            try:
                self.driver.execute_script(
                    "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight));"
                )
                self._random_delay(1.0, 2.0)
            except Exception:
                pass
            for url in collect(self):
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)
            unchanged_rounds = unchanged_rounds + 1 if len(all_urls) == before else 0
            if unchanged_rounds >= 3:
                break
        return all_urls[:target]

    def search(self, keyword):
        search_url = build_noon_search_url(keyword, self.region)
        print(f'Opening Noon search URL directly: {search_url}')
        self.driver.get(search_url)
        self._random_delay(4.0, 6.0)
        if self._detect_captcha():
            print('Noon verification/challenge detected.')
            save_search_diagnostics(self, self.region, 'challenge')
            self.last_search_urls = []
            return False
        self.wait_for_results()
        self.last_search_urls = self.scroll_and_collect()
        print(f'FINAL SEARCH RESULT COUNT: {len(self.last_search_urls)}')
        if not self.last_search_urls:
            save_search_diagnostics(self, self.region, 'empty')
            return False
        print(f'FIRST PRODUCT URL: {self.last_search_urls[0]}')
        return True

    scraper.search_keyword = types.MethodType(search, scraper)
    scraper._collect_search_page_product_urls = types.MethodType(collect, scraper)
    scraper._scroll_and_collect_search_results = types.MethodType(scroll_and_collect, scraper)
    scraper.wait_for_results = types.MethodType(wait_for_results, scraper)


def install_product_fallbacks(scraper):
    original = scraper.scrape_product_details

    def scrape_details(self, product_url, keyword):
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
                continue
        for selector in ('strong.amount', '[class*="priceNowText"]', '[class*="priceNow"]'):
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    value = elements[0].text.strip()
                    if value:
                        currency = 'SAR' if self.region == 'ksa' else 'AED'
                        price = value if currency in value else f'{currency} {value}'
                        break
            except Exception:
                continue
        if rows:
            for row in rows:
                if title and (not row.get('Title') or row.get('Title') == 'N/A'):
                    row['Title'] = title
                if price and (not row.get('Price') or row.get('Price') == 'N/A'):
                    row['Price'] = price
        return rows

    scraper.scrape_product_details = types.MethodType(scrape_details, scraper)


for region in regions:
    scraper = NoonScraper(headless=True, region=region)
    try:
        install_robust_noon_search(scraper, request['max_products'])
        install_product_fallbacks(scraper)
        data = scraper.scrape(request['keywords'], request['max_products'])
        all_data.extend(data)
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
