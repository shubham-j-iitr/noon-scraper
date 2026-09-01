"""
Noon Web Scraper Module
Handles scraping of product data from noon.com
Production Hardened: Includes retry logic, validation, and anti-bot measures
"""

import re
import time
import random
import logging
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import *
from validators import validate_product_data

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),  # Clear log file on each run
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)




from urllib.parse import quote_plus, urlsplit, urlunsplit


def build_noon_search_url(keyword: str, region: str) -> str:
    """Build Noon's native search URL for a keyword.

    Examples:
        UAE: https://www.noon.com/uae-en/search/?q=iPhone+15
        KSA: https://www.noon.com/saudi-en/search/?q=iPhone+15
    """
    region_key = region.lower().strip()
    if region_key not in REGIONS:
        raise ValueError(f"Unsupported region: {region}")
    base_search_url = REGIONS[region_key]['search_url']
    return f"{base_search_url}{quote_plus(keyword.strip())}"


def normalize_product_url(href: str) -> str:
    """Normalize a Noon product URL so tracking/query parameters do not create duplicates."""
    if not href:
        return ''
    try:
        parts = urlsplit(href)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    except Exception:
        return href.split('?', 1)[0]


def extract_noon_product_urls(hrefs):
    """Return unique Noon product URLs from browser links."""
    urls = []
    seen = set()
    for href in hrefs:
        if not href or '/p/' not in href or 'noon.com' not in href.lower():
            continue
        url = normalize_product_url(href)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls

class NoonScraper:
    """Main scraper class for noon.com"""
    
    def __init__(self, headless=False, region='uae', proxy=None):
        """
        Initialize the scraper
        
        Args:
            headless (bool): Run browser in headless mode
            region (str): Region to scrape ('uae' or 'ksa')
            proxy (str): Optional proxy URL, e.g. 'http://user:pass@host:port'
                         Required when running from outside UAE/KSA (geo-block bypass)
        """
        self.headless = headless
        self.proxy = proxy
        self.driver = None
        self.scraped_data = []
        self.last_search_urls = []
        
        # Store REGIONS as class attribute for region switching
        self.REGIONS = REGIONS
        
        # Set region
        self.region = region.lower()
        if self.region not in REGIONS:
            logger.warning(f"Invalid region '{region}', defaulting to UAE")
            self.region = 'uae'
        
        # Set URLs based on region
        self.base_url = REGIONS[self.region]['base_url']
        self.search_url = REGIONS[self.region]['search_url']
        logger.info(f"Scraper initialized for region: {REGIONS[self.region]['name']}")
    
    def __del__(self):
        """Destructor to ensure WebDriver cleanup"""
        self.close()
    
    def close(self):
        """Close WebDriver and cleanup resources"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup"""
        self.close()
        return False  # Don't suppress exceptions
    
    
    def _get_system_proxy(self):
        """
        Read Windows system proxy settings (set by proxy-mode VPNs).
        Returns proxy string like 'http://host:port' or None.
        Note: TUN-mode VPNs (e.g. Urban VPN) don't expose a local proxy port —
              use the --proxy flag with a real UAE/KSA proxy URL in that case.
        """
        try:
            import winreg
            reg_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                proxy_enabled, _ = winreg.QueryValueEx(key, 'ProxyEnable')
                if proxy_enabled:
                    proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
                    if proxy_server:
                        if not proxy_server.startswith('http'):
                            proxy_server = f'http://{proxy_server}'
                        return proxy_server
        except Exception:
            pass
        return None

    def _init_driver(self):
        """Initialize a standard Selenium Chrome/Chromium browser.

        The web version intentionally uses the normal Chrome driver rather than
        an undetected driver. This keeps deployment simpler on free containers
        and avoids browser fingerprint/anti-bot evasion techniques.
        """
        logger.info("Initializing standard Chrome WebDriver...")

        import os
        chrome_options = webdriver.ChromeOptions()

        for browser_binary in (
            '/usr/bin/google-chrome',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
        ):
            if os.path.exists(browser_binary):
                chrome_options.binary_location = browser_binary
                logger.info(f"Using browser binary: {browser_binary}")
                break

        if self.headless:
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--window-size=1920,1080')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=en-US')
        chrome_options.add_argument('--accept-lang=en-US,en;q=0.9')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')

        effective_proxy = self.proxy
        if effective_proxy:
            chrome_options.add_argument(f'--proxy-server={effective_proxy}')
            logger.info("Using configured proxy")

        chromedriver = os.getenv('CHROMEDRIVER_PATH', '').strip()
        if not chromedriver and os.path.exists('/usr/bin/chromedriver'):
            chromedriver = '/usr/bin/chromedriver'

        if chromedriver:
            self.driver = webdriver.Chrome(service=Service(chromedriver), options=chrome_options)
        else:
            self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        logger.info("WebDriver initialized successfully")

    def is_session_valid(self):
        """Check if the current browser session is still alive"""
        if not self.driver:
            return False
        try:
            _ = self.driver.title  # Simple command to test session
            return True
        except Exception:
            logger.warning("Browser session is no longer valid")
            return False
    
    def restart_driver(self):
        """Safely tear down the dead browser and start a fresh one"""
        logger.info("Restarting browser...")
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass  # Browser may already be dead
        self.driver = None
        self._init_driver()
        logger.info("Browser restarted successfully")
    
    def _random_delay(self, min_delay=REQUEST_DELAY_MIN, max_delay=REQUEST_DELAY_MAX):
        """Add random delay to mimic human behavior (using Gaussian distribution)"""
        # Use Gaussian distribution for more natural delays
        mean = (min_delay + max_delay) / 2
        std_dev = (max_delay - min_delay) / 4
        delay = random.gauss(mean, std_dev)
        # Clamp to min/max bounds
        delay = max(min_delay, min(delay, max_delay))
        time.sleep(delay)
    
    def _simulate_human_behavior(self):
        """Simulate human-like mouse movements and scrolling"""
        try:
            # Random small scrolls
            scroll_amount = random.randint(100, 300)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.5))
            
            # Occasional mouse movement (not visible in headless but logged)
            if random.random() < 0.3:  # 30% chance
                try:
                    body = self.driver.find_element(By.TAG_NAME, 'body')
                    actions = ActionChains(self.driver)
                    actions.move_to_element_with_offset(body, random.randint(0, 100), random.randint(0, 100))
                    actions.perform()
                except Exception as e:
                    logger.debug(f"Mouse movement failed: {e}")
        except Exception as e:
            logger.debug(f"Error simulating human behavior: {e}")
    
    def _safe_find_element(self, by, selector, timeout=None, parent=None):
        """
        Safely find element with wait
        
        Args:
            by: Selenium By locator
            selector: CSS selector or XPath
            timeout: Wait timeout (uses ELEMENT_WAIT_TIMEOUT if None)
            parent: Parent element to search within
            
        Returns:
            WebElement or None
        """
        try:
            # Use default timeout if not specified
            if timeout is None:
                timeout = ELEMENT_WAIT_TIMEOUT
            
            element_source = parent if parent else self.driver
            element = WebDriverWait(element_source, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            return None
    
    def _safe_find_elements(self, by, selector, timeout=None, parent=None):
        """
        Safely find multiple elements
        
        Args:
            by: Selenium By locator
            selector: CSS selector or XPath
            timeout: Wait timeout (uses ELEMENT_WAIT_TIMEOUT if None)
            parent: Parent element to search within
            
        Returns:
            List of WebElements
        """
        try:
            # Use default timeout if not specified
            if timeout is None:
                timeout = ELEMENT_WAIT_TIMEOUT
                
            element_source = parent if parent else self.driver
            WebDriverWait(element_source, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element_source.find_elements(by, selector)
        except TimeoutException:
            return []
    
    def _get_text_safe(self, element, selector=None):
        """
        Safely extract text from element
        
        Args:
            element: WebElement or driver
            selector: Optional CSS selector
            
        Returns:
            str: Extracted text or empty string
        """
        try:
            if selector:
                target = element.find_element(By.CSS_SELECTOR, selector)
            else:
                target = element
            return target.text.strip()
        except Exception as e:
            logger.debug(f"Error extracting text: {e}")
            return ""
    
    def _detect_captcha(self):
        """
        Detect if CAPTCHA is present on current page
        
        Returns:
            bool: True if CAPTCHA detected, False otherwise
        """
        try:
            # Common CAPTCHA indicators
            captcha_selectors = [
                'iframe[src*="recaptcha"]',  # Google reCAPTCHA
                'iframe[src*="hcaptcha"]',   # hCaptcha
                '[class*="captcha"]',         # Generic captcha classes
                '[id*="captcha"]',            # Generic captcha IDs
                '#challenge-form',            # Cloudflare challenge
                '.cf-challenge',              # Cloudflare
            ]
            
            for selector in captcha_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.warning(f" CAPTCHA DETECTED: {selector}")
                    return True
            
            # Check page text for CAPTCHA keywords
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            captcha_keywords = ['verify you are human', 'captcha', 'security check', 'unusual traffic']
            for keyword in captcha_keywords:
                if keyword in page_text:
                    logger.warning(f" CAPTCHA DETECTED: Found keyword '{keyword}'")
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Error detecting CAPTCHA: {e}")
            return False
    
    # ============================================================================
    # SEARCH AND NAVIGATION
    # ============================================================================
    
    def _collect_search_page_product_urls(self):
        """Collect Noon product links currently present on the loaded search page."""
        hrefs = []
        try:
            links = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS['product_links'])
        except Exception:
            links = []

        for link in links:
            try:
                href = link.get_attribute('href')
                if href:
                    hrefs.append(href)
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        return extract_noon_product_urls(hrefs)

    def _click_load_more_if_present(self):
        """Click a visible Load More/Show More button when Noon exposes one."""
        if not LOAD_MORE_ENABLED:
            return False

        try:
            buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more') "
                "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]"
            )
            for button in buttons:
                try:
                    if not button.is_displayed() or not button.is_enabled():
                        continue
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
                    time.sleep(0.5)
                    button.click()
                    logger.info("Clicked Noon 'Load More/Show More' button")
                    return True
                except Exception:
                    continue
        except Exception as exc:
            logger.debug(f"Could not inspect Load More button: {exc}")
        return False

    def _scroll_and_collect_search_results(self):
        """Scroll Noon's native search page and collect product URLs as they lazy-load."""
        all_urls = []
        seen = set()
        previous_count = 0
        stable_rounds = 0

        logger.info("Scrolling Noon search results to load products...")

        for scroll_num in range(1, MAX_SCROLLS + 1):
            # Collect links before the scroll as well as after it so the first
            # viewport is never missed.
            for url in self._collect_search_page_product_urls():
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)

            current_height = self.driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
            )
            self.driver.execute_script("window.scrollTo({top: arguments[0], behavior: 'smooth'});", current_height)
            self._random_delay(SCROLL_DELAY_MIN, max(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))

            clicked = self._click_load_more_if_present()
            if clicked:
                self._random_delay(1.0, 2.0)

            for url in self._collect_search_page_product_urls():
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)

            logger.info(f"Search scroll {scroll_num}/{MAX_SCROLLS}: {len(all_urls)} unique product URLs")

            if MAX_PRODUCTS_PER_KEYWORD and len(all_urls) >= MAX_PRODUCTS_PER_KEYWORD:
                break

            if len(all_urls) == previous_count and not clicked:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_count = len(all_urls)

            # One unchanged round is common while lazy-loading catches up; two
            # consecutive unchanged rounds is a safer end-of-results signal.
            if stable_rounds >= 2:
                logger.info("No new product URLs after consecutive scrolls; reached end of search results")
                break

        return all_urls

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        retry=retry_if_exception_type((TimeoutException, ConnectionError)),
        reraise=True
    )
    def search_keyword(self, keyword):
        """Open Noon's native search page directly and collect product URLs."""
        try:
            search_url = build_noon_search_url(keyword, self.region)
            logger.info(f"Opening Noon search URL: {search_url}")
            self.driver.get(search_url)
            self._random_delay(SEARCH_PAGE_INITIAL_DELAY_MIN, SEARCH_PAGE_INITIAL_DELAY_MAX)

            if self._detect_captcha():
                logger.warning("Noon returned a verification/challenge page; stopping this search.")
                self.last_search_urls = []
                return False

            self.last_search_urls = self._scroll_and_collect_search_results()
            logger.info(f"Found {len(self.last_search_urls)} Noon product links for '{keyword}'")
            return bool(self.last_search_urls)
        except Exception as e:
            logger.error(f"Error searching Noon for keyword '{keyword}': {e}")
            raise

    # ============================================================================
    # DATA EXTRACTION METHODS
    # ============================================================================
    
    def _extract_category(self):
        """Extract category from breadcrumbs"""
        try:
            breadcrumbs = self._safe_find_elements(By.CSS_SELECTOR, SELECTORS['breadcrumbs'])
            if breadcrumbs:
                # Get all breadcrumb texts except "Home"
                categories = [bc.text.strip() for bc in breadcrumbs if bc.text.strip() and bc.text.strip().lower() != 'home']
                return ' > '.join(categories) if categories else "N/A"
            return "N/A"
        except Exception as e:
            logger.debug(f"Error extracting category: {e}")
            return "N/A"
    
    def _extract_description(self):
        """Extract product description/highlights"""
        try:
            # Try to find highlights section
            highlights = self._safe_find_elements(By.CSS_SELECTOR, SELECTORS['highlights'])
            if highlights:
                desc_parts = [h.text.strip() for h in highlights[:3]]  # Get first 3 highlights
                return ' | '.join(desc_parts) if desc_parts else "N/A"
            return "N/A"
        except Exception as e:
            logger.debug(f"Error extracting description: {e}")
            return "N/A"
    
    def _extract_grade(self):
        """Extract product grade/condition (Optimized)"""
        try:
            # 1. Check Specifications Table (Most Reliable)
            try:
                spec_rows = self.driver.find_elements(By.CSS_SELECTOR, 'table tr')
                for row in spec_rows:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 2 and cells[0].text.strip().lower() == 'grade':
                        return cells[1].text.strip()
            except:
                pass
            
            # 2. Unified Text Search (Title, Description, Page)
            # Gather all relevant text sources
            title = self._get_text_safe(self.driver, SELECTORS['product_title']).lower()
            desc = self._extract_description().lower()
            
            # Use cached page text for broad search
            try:
                page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            except:
                page_text = ""

            # Grade Keywords Map
            grade_keywords = {
                'excellent': 'Excellent', 'very good': 'Very Good', 'good': 'Good',
                'fair': 'Fair', 'like new': 'Like New', 'grade a': 'Grade A',
                'grade b': 'Grade B', 'grade c': 'Grade C', 'pristine': 'Pristine',
                'mint': 'Mint', 'max': 'Max', 'premium': 'Premium'
            }
            
            # Check Title & Description first (High Confidence)
            for keyword, grade in grade_keywords.items():
                if keyword in title or keyword in desc:
                    return grade

            # Check specific "Condition: X" patterns in page text
            for keyword, grade in grade_keywords.items():
                if f'condition {keyword}' in page_text or f'grade {keyword}' in page_text:
                    return grade

            # 3. Fallback: Implicit "Renewed" status
            if 'renewed' in title or 'refurbished' in title:
                logger.info("Product is renewed but no specific grade found - defaulting to 'Renewed'")
                return "Renewed"
            
            return "N/A"
        except Exception as e:
            logger.error(f"Error extracting grade: {str(e)}")
            return "N/A"
    
    def _extract_express_delivery(self):
        """Extract express delivery type (Optimized)"""
        try:
            # 1. Visual Badge Check (Most Reliable)
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, 'img[alt*="noon-express"], img[src*="fulfilment_express"]'):
                    return "Express Delivery"
            except:
                pass
            
            # 2. Text Search in Page
            page_text = self._get_page_text()
            delivery_types = [
                ('same day delivery', 'Same Day Delivery'),
                ('next day delivery', 'Next Day Delivery'),
                ('express delivery', 'Express Delivery'),
                ('noon express', 'Noon Express')
            ]
            
            for keyword, delivery_type in delivery_types:
                if keyword in page_text:
                    return delivery_type
            
            return "Standard Delivery"
        except Exception as e:
            logger.debug(f"Error extracting express delivery: {str(e)}")
            return "N/A"
    
    # ============================================================================
    # HELPER METHODS - Keyword Matching and Filtering
    # ============================================================================
    



    
    # ============================================================================
    # SELLER EXTRACTION
    # ============================================================================
    
    def _extract_sellers(self, product_url):
        """
        Extract all sellers for a product
        
        Args:
            product_url (str): Product URL
            
        Returns:
            list: List of seller dictionaries
        """
        sellers = []
        
        try:
            # Wait for price element to load with optimized timeout
            price_element = self._safe_find_element(By.CSS_SELECTOR, SELECTORS['price_now'], timeout=ELEMENT_WAIT_TIMEOUT_CRITICAL)
            
            # Find primary seller
            primary_seller = self._get_text_safe(self.driver, SELECTORS['seller_name'])
            
            # Extract price using JavaScript textContent (more reliable than .text)
            if price_element:
                try:
                    price_text = self.driver.execute_script("return arguments[0].textContent;", price_element)
                    # Clean price text - remove any non-printable characters and extra whitespace
                    if price_text:
                        price_text = re.sub(r'[^\x20-\x7E]', '', price_text)  # Keep only printable ASCII
                        price_text = price_text.strip()
                        
                        # Determine currency based on region
                        currency = "SAR" if self.region == 'ksa' else "AED"
                        
                        primary_price = f"{currency} {price_text}" if price_text else "N/A"
                    else:
                        primary_price = "N/A"
                except:
                    primary_price = "N/A"
            else:
                primary_price = "N/A"
            
            primary_rating = self._get_text_safe(self.driver, SELECTORS['rating_value'])
            
            # Log price extraction for debugging
            if primary_price == "N/A":
                logger.warning(f"Price not found for product. Tried selector: {SELECTORS['price_now']}")
            else:
                logger.info(f"Extracted price: {primary_price}")
            
            # Always add primary seller (default to 'noon' if not found)
            sellers.append({
                'name': primary_seller if primary_seller else 'N/A',
                'price': primary_price,
                'rating': primary_rating
            })
            
            # Always check for other sellers button
            try:
                # Look for "other seller" button using XPath
                other_sellers_buttons = self.driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'other seller')]")
                
                if other_sellers_buttons:
                    logger.info(f"Found 'Other Sellers' button, clicking to view all sellers...")
                    
                    # Click the button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", other_sellers_buttons[0])
                    time.sleep(0.3)  # Reduced from 0.5s
                    other_sellers_buttons[0].click()
                    
                    # Wait for modal to appear (reduced wait time)
                    time.sleep(0.5)  # Further reduced from 1s
                    
                    # Extract sellers from modal (with faster timeout)
                    modal_sellers = self._safe_find_elements(By.CSS_SELECTOR, SELECTORS['modal_sellers'], timeout=ELEMENT_WAIT_TIMEOUT_FAST)
                    
                    logger.info(f"Found {len(modal_sellers)} seller cards in modal")
                    
                    for seller_card in modal_sellers:
                        try:
                            seller_name = self._get_text_safe(seller_card, SELECTORS['modal_seller_name'])
                            seller_price = self._get_text_safe(seller_card, SELECTORS['modal_seller_price'])
                            seller_rating = self._get_text_safe(seller_card, SELECTORS['modal_seller_rating'])
                            
                            # Avoid duplicates
                            if seller_name and not any(s['name'] == seller_name for s in sellers):
                                sellers.append({
                                    'name': seller_name,
                                    'price': seller_price if seller_price else primary_price,
                                    'rating': seller_rating if seller_rating else 'N/A'
                                })
                        except:
                            continue
                    
                    # Close modal (optimized)
                    try:
                        close_buttons = self.driver.find_elements(By.CSS_SELECTOR, SELECTORS['close_modal'])
                        if close_buttons:
                            close_buttons[0].click()
                            time.sleep(0.2)  # Further reduced from 0.3s
                        else:
                            # Press ESC key
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                            time.sleep(0.2)  # Further reduced from 0.3s
                    except:
                        pass
                            
            except Exception as e:
                logger.debug(f"No other sellers found or error accessing modal: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error extracting sellers: {str(e)}")
        
        # If no sellers found, add default
        if not sellers:
            sellers.append({
                'name': 'N/A',
                'price': 'N/A',
                'rating': 'N/A'
            })
        
        return sellers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((TimeoutException, StaleElementReferenceException, ConnectionError)),
        reraise=True
    )
    def scrape_product_details(self, product_url, keyword):
        """
        Scrape details from a single product page (with retry logic & validation)
        
        Args:
            product_url (str): URL of product
            keyword (str): Search keyword used
            
        Returns:
            list: List of product data dictionaries (one per seller)
        """
        product_data_list = []
        
        try:
            logger.info(f"Scraping product: {product_url}")
            
            # Navigate to product page
            self.driver.get(product_url)
            
            # ANTI-BOT: More human-like delay with variability
            self._random_delay(PRODUCT_DETAIL_DELAY, PRODUCT_DETAIL_DELAY + 0.5)
            
            # ANTI-BOT: Simulate human behavior occasionally
            if random.random() < 0.05:  # 5% of the time (reduced from 30%)
                self._simulate_human_behavior()
            
            # Single scroll to load content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            self._random_delay(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX)
            
            # Extract common product information
            title = self._get_text_safe(self.driver, SELECTORS['product_title'])
            
            category = self._extract_category()
            description = self._extract_description()
            
            # Extract rating and reviews with faster timeout
            rating_element = self._safe_find_element(By.CSS_SELECTOR, SELECTORS['rating_value'], timeout=ELEMENT_WAIT_TIMEOUT_FAST)
            rating = self._get_text_safe(rating_element) if rating_element else "N/A"
            
            reviews_element = self._safe_find_element(By.CSS_SELECTOR, SELECTORS['reviews_count'], timeout=ELEMENT_WAIT_TIMEOUT_FAST)
            reviews = self._get_text_safe(reviews_element) if reviews_element else "N/A"
            
            # Extract all sellers (includes price extraction)
            sellers = self._extract_sellers(product_url)
            
            # Extract grade and express delivery
            grade = self._extract_grade()
            express_delivery = self._extract_express_delivery()
            
            # Create a row for each seller
            for seller in sellers:
                product_data = {
                    'Search Keyword': keyword,
                    'Category': category,
                    'Title': title,
                    'Description': description,
                    'Price': seller['price'],
                    'Rating': rating,
                    'Reviews': reviews,
                    'Seller': seller['name'],
                    'Grade': grade,
                    'Delivery': express_delivery,
                    'Region': REGIONS[self.region]['name'],
                    'Product URL': product_url,
                    'Platform': 'Noon'
                }
                
                # VALIDATION: Validate scraped data
                is_valid, errors = validate_product_data(product_data, keyword)
                if not is_valid:
                    logger.warning(f"Validation failed for {product_url}: {', '.join(errors)}")
                    # Still add to list but log the issue
                
                product_data_list.append(product_data)
            
            logger.info(f"Scraped product with {len(sellers)} seller(s)")
            
        except Exception as e:
            logger.error(f"Error scraping product {product_url}: {str(e)}")
            raise  # Raise for retry logic
        
        return product_data_list
    
    def scrape_search_results(self, keyword, max_products=None, seen_urls=None):
        """
        Scrape all products from search results with pagination support
        
        Args:
            keyword (str): Search keyword
            max_products (int): Maximum number of products to scrape (None for all)
            seen_urls (set): Set of already scraped URLs to avoid duplicates
            
        Returns:
            list: List of all scraped product data
        """
        all_data = []
        if seen_urls is None:
            seen_urls = set()
        
        try:
            # Open Noon's native search page, scroll it, and collect product URLs.
            if not self.search_keyword(keyword):
                return all_data

            product_urls = list(self.last_search_urls)

            # Final fallback: collect every visible product link currently in the DOM.
            if not product_urls:
                product_urls = self._collect_search_page_product_urls()
            
            if not product_urls:
                logger.warning("No product URLs found on search results page")
                return all_data
            
            # Limit if max_products specified
            if max_products:
                # 3x buffer so we still hit the max_products target after skipping duds
                product_urls = product_urls[:max_products * 3]
            
            logger.info(f"Found {len(product_urls)} unique products to scrape")
            
            # Track filtering statistics
            total_checked = 0
            total_scraped = 0
            total_filtered = 0
            
            # Filter out already seen URLs
            unique_product_urls = []
            skipped_count = 0
            
            for url in product_urls:
                # Normalize URL to avoid duplicates (remove query params if needed, but keeping simple for now)
                if url not in seen_urls:
                    unique_product_urls.append(url)
                    seen_urls.add(url)
                else:
                    skipped_count += 1
            
            if skipped_count > 0:
                logger.info(f"Skipping {skipped_count} already scraped products")
            
            product_urls = unique_product_urls
            
            if not product_urls:
                logger.info("No new unique products found to scrape for this keyword")
                return all_data

            # Scrape each product with progress bar
            for url in tqdm(product_urls, desc=f"Scraping '{keyword}'", unit="product", position=1, leave=False):
                total_checked += 1
                product_data = self.scrape_product_details(url, keyword)
                
                if product_data:
                    all_data.extend(product_data)
                    total_scraped += 1
                    
                    # Stop if we have enough valid products
                    if max_products and total_scraped >= max_products:
                        logger.info(f"Reached target distinct products count ({max_products})")
                        break
                else:
                    total_filtered += 1
                
                # Random delay between products
                self._random_delay()
            
            
            logger.info(f"Completed scraping {total_scraped} products")
            
        except Exception as e:
            logger.error(f"Error scraping search results: {str(e)}")
        
        return all_data
    
    def _create_not_found_row(self, keyword):
        """
        Create a placeholder row for keywords that don't find any products
        
        Args:
            keyword (str): Search keyword that didn't find products
            
        Returns:
            dict: Placeholder product data dictionary
        """
        return {
            'Search Keyword': keyword,
            'Category': 'Not Found',
            'Title': 'No products found for this keyword',
            'Description': 'N/A',
            'Price': 'N/A',
            'Rating': 'N/A',
            'Reviews': 'N/A',
            'Seller': 'N/A',
            'Grade': 'N/A',
            'Delivery': 'N/A',
            'Region': REGIONS[self.region]['name'],
            'Product URL': 'N/A'
        }
    
    def scrape(self, keywords, max_products_per_keyword=None):
        """
        Main scraping method
        
        Args:
            keywords (list or str): Keyword(s) to search
            max_products_per_keyword (int): Max products per keyword
            
        Returns:
            list: All scraped data
        """
        # Convert single keyword to list
        if isinstance(keywords, str):
            keywords = [keywords]
        
        try:
            # Initialize driver
            self._init_driver()
            
            # Create overall progress bar for all keywords
            overall_pbar = tqdm(total=len(keywords), desc="Overall Progress", unit="keyword", position=0, leave=True)
            
            # Scrape each keyword
            for idx, keyword in enumerate(keywords, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"Starting scrape for keyword: '{keyword}' ({idx}/{len(keywords)})")
                logger.info(f"{'='*60}\n")
                
                data = self.scrape_search_results(keyword, max_products_per_keyword)
                
                # SOFT RETRY: If no products found, try one more time after a delay
                if not data:
                    logger.warning(f"No products found for keyword '{keyword}' on first attempt. Retrying in 10s...")
                    time.sleep(10)
                    self.restart_driver() # Fresh browser session for retry
                    data = self.scrape_search_results(keyword, max_products_per_keyword)

                # If still no products found, add a placeholder row
                if not data:
                    logger.warning(f"No products found for keyword '{keyword}' after retry - adding placeholder row")
                    placeholder_row = self._create_not_found_row(keyword)
                    self.scraped_data.append(placeholder_row)
                    logger.info(f"Added 'Not Found' placeholder row for keyword '{keyword}'")
                else:
                    self.scraped_data.extend(data)
                    logger.info(f"Scraped {len(data)} rows for keyword '{keyword}'")
                
                # Update overall progress
                overall_pbar.update(1)
            
            # Close overall progress bar
            overall_pbar.close()
            
            logger.info(f"\n{'='*60}")
            logger.info(f"SCRAPING COMPLETED")
            logger.info(f"Total rows scraped: {len(self.scraped_data)}")
            logger.info(f"{'='*60}\n")
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
        
        finally:
            # Close driver
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")
        
        return self.scraped_data
    
    def get_data(self):
        """Return scraped data"""
        return self.scraped_data
