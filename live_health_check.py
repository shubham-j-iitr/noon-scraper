import logging
import sys
import os
from noon_scraper import NoonScraper

# Configure logging to show info in console
# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass  # If it fails, continue without UTF-8

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("HealthCheck")

def run_live_check(headless=False, proxy=None):
    print("\n" + "="*60)
    mode_label = "HEADLESS" if headless else "VISIBLE BROWSER"
    proxy_label = f" | PROXY: {proxy.split('@')[-1] if proxy and '@' in proxy else proxy or 'none'}"
    print(f"STARTING FULL LIVE HEALTH CHECK (UAE + KSA) [{mode_label}{proxy_label}]")
    print("="*60)
    
    regions = ['uae', 'ksa']
    keyword = "iphone"
    results_summary = {}
    
    for region in regions:
        print(f"\nTesting Region: {region.upper()}...")
        logger.info(f"[{region.upper()}] Target: Scrape 1 item for keyword '{keyword}'")

        scraper = None
        try:
            scraper = NoonScraper(headless=headless, region=region, proxy=proxy)
            scraper._init_driver()
            
            logger.info(f"[{region.upper()}] Scraper initialized successfully")
            
            # Log current URL + page title to detect CAPTCHA/redirects
            try:
                current_url = scraper.driver.current_url
                page_title = scraper.driver.title
                logger.info(f"[{region.upper()}] Starting URL: {current_url}")
                logger.info(f"[{region.upper()}] Page title: {page_title}")
            except Exception:
                pass

            # Scrape 1 item
            results = scraper.scrape_search_results(keyword, max_products=1)

            # Log post-search URL + title so we can detect bot walls
            try:
                current_url = scraper.driver.current_url
                page_title  = scraper.driver.title
                print(f"   URL  : {current_url[:100]}")
                print(f"   Title: {page_title}")
            except Exception:
                pass
            
            if results:
                print(f"[PASS] {region.upper()} CHECK PASSED")
                print(f"   Items found: {len(results)}")
                title_preview = (results[0].get('Title') or '')[:50]
                print(f"   Sample: {title_preview}... | {results[0].get('Price')}")
                results_summary[region] = True
            else:
                print(f"[FAIL] {region.upper()} CHECK FAILED: No results found")
                results_summary[region] = False
                
        except Exception as e:
            print(f"[FAIL] {region.upper()} CHECK FAILED: Exception occurred")
            print(f"   Error: {str(e)}")
            logger.exception(f"[{region.upper()}] Detailed error:")
            results_summary[region] = False
            
        finally:
            if scraper:
                scraper.close()
                print(f"[{region.upper()}] Browser closed")
    
    # Final Summary
    print("\n" + "="*60)
    print("HEALTH CHECK SUMMARY")
    print("="*60)
    all_passed = True
    for region, passed in results_summary.items():
        status = "PASSED" if passed else "FAILED"
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"{icon} {region.upper()}: {status}")
        if not passed:
            all_passed = False
    print("="*60 + "\n")
    
    return all_passed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Noon scraper live health check")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run in headless mode (default: visible browser). Noon often blocks headless."
    )
    parser.add_argument(
        "--proxy",
        default=os.environ.get("NOON_PROXY"),
        help="Proxy URL to bypass geo-block, e.g. http://user:pass@host:port. "
             "Can also be set via NOON_PROXY environment variable."
    )
    args = parser.parse_args()
    success = run_live_check(headless=args.headless, proxy=args.proxy)
    sys.exit(0 if success else 1)
