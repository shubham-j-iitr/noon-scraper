import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from excel_exporter import ExcelExporter

request = json.loads(open('data/request.json', encoding='utf-8').read())
region = request['region']
keyword = request['keywords'][0]
target = 1

debug_dir = Path('debug')
debug_dir.mkdir(parents=True, exist_ok=True)


def diagnostics(driver, stage):
    prefix = debug_dir / f'noon-direct-{stage}'
    try:
        driver.save_screenshot(str(prefix.with_suffix('.png')))
    except Exception as exc:
        print(f'Diagnostic screenshot failed: {exc}')
    try:
        prefix.with_suffix('.html').write_text(driver.page_source, encoding='utf-8')
    except Exception as exc:
        print(f'Diagnostic HTML failed: {exc}')
    try:
        body = driver.find_element(By.TAG_NAME, 'body').text
        prefix.with_suffix('.txt').write_text(body[:30000], encoding='utf-8')
        print(f'Diagnostic title: {driver.title}')
        print(f'Diagnostic URL: {driver.current_url}')
        print(f'Diagnostic body: {body[:2000]!r}')
    except Exception as exc:
        print(f'Diagnostic body failed: {exc}')


def make_driver():
    options = webdriver.ChromeOptions()
    chrome_bin = os.environ.get('CHROME_BIN', '').strip()
    driver_bin = os.environ.get('CHROMEDRIVER_PATH', '').strip()
    if chrome_bin and os.path.exists(chrome_bin):
        options.binary_location = chrome_bin
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

    if driver_bin and os.path.exists(driver_bin):
        driver = webdriver.Chrome(service=Service(driver_bin), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(12)
    driver.set_script_timeout(10)
    print(f'Chrome binary: {options.binary_location}')
    print(f'ChromeDriver: {driver_bin or "Selenium Manager"}')
    print('Chrome network mode: HTTP/1.1 (--disable-http2, --disable-quic)')
    return driver


def collect_product_urls(driver):
    urls = []
    seen = set()
    for link in driver.find_elements(By.CSS_SELECTOR, 'a[href]'):
        try:
            href = urljoin('https://www.noon.com', link.get_attribute('href') or '')
            if 'noon.com' in href and ('/p/' in href or '/product/' in href):
                if href not in seen:
                    seen.add(href)
                    urls.append(href)
        except Exception:
            pass
    return urls


def extract_first_text(driver, selectors):
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                text = element.text.strip()
                if text:
                    return text
        except Exception:
            pass
    return ''


def scrape_one():
    driver = make_driver()
    search_url = f'https://www.noon.com/{"uae-en" if region == "uae" else "sa-en"}/search/?q={keyword.replace(" ", "+")}'
    try:
        print(f'Opening Noon search URL directly: {search_url}')
        try:
            driver.get(search_url)
        except TimeoutException as exc:
            print(f'Search navigation timed out; continuing with loaded DOM: {exc}')
        time.sleep(5)

        product_urls = collect_product_urls(driver)
        for scroll in range(1, 9):
            if product_urls:
                break
            driver.execute_script('window.scrollBy(0, Math.max(700, window.innerHeight * 0.9));')
            time.sleep(1.5)
            product_urls = collect_product_urls(driver)
            print(f'Search scroll {scroll}/8: {len(product_urls)} product URLs')

        if not product_urls:
            diagnostics(driver, 'empty-search')
            raise RuntimeError('TEST FAILED: Noon search page returned no product URLs')

        product_url = product_urls[0]
        print(f'FIRST PRODUCT URL: {product_url}')
        try:
            driver.get(product_url)
        except TimeoutException as exc:
            print(f'Product navigation timed out; continuing with loaded DOM: {exc}')
        time.sleep(4)

        title = extract_first_text(driver, ['h1', '[data-qa="product-name"]'])
        price = extract_first_text(driver, [
            'strong.amount',
            '[data-qa="product-price"]',
            '[class*="priceNowText"]',
            '[class*="priceNow"]',
        ])

        if not price:
            body = driver.find_element(By.TAG_NAME, 'body').text
            match = re.search(r'(?:AED|SAR)\s*[\d,]+(?:\.\d+)?', body, flags=re.I)
            if match:
                price = match.group(0).strip()

        if not title or not price:
            diagnostics(driver, 'product-missing-data')
            raise RuntimeError(f'TEST FAILED: product page loaded but title/price missing. title={title!r}, price={price!r}')

        row = {
            'Keyword': keyword,
            'Region': 'UAE' if region == 'uae' else 'KSA',
            'Title': title,
            'Price': price,
            'Product URL': product_url,
        }
        return row
    finally:
        try:
            driver.quit()
        except Exception:
            pass


row = scrape_one()
path = ExcelExporter().export_to_excel([row])
shutil.copy2(path, 'output/result.xlsx')
print('TEST PASSED: exactly 1 real Noon product was scraped.')
print(f"PRODUCT: {row['Title']} | PRICE: {row['Price']} | URL: {row['Product URL']}")
