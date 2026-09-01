import os
"""
Configuration settings for Noon Web Scraper
"""

# Region settings
REGIONS = {
    'uae': {
        'name': 'UAE',
        'base_url': 'https://www.noon.com/uae-en',
        'search_url': 'https://www.noon.com/uae-en/search/?q='
    },
    'ksa': {
        'name': 'KSA',
        'base_url': 'https://www.noon.com/saudi-en',
        'search_url': 'https://www.noon.com/saudi-en/search/?q='
    }
}

# Default region (can be changed)
DEFAULT_REGION = 'uae'

# Legacy support (will be set based on region)
BASE_URL = REGIONS[DEFAULT_REGION]['base_url']
SEARCH_URL = REGIONS[DEFAULT_REGION]['search_url']

# Search mode
# The scraper always uses Noon's native search page directly. No Google/Noon API is used.
SEARCH_PAGE_INITIAL_DELAY_MIN = float(os.getenv('SEARCH_PAGE_INITIAL_DELAY_MIN', '2.0'))
SEARCH_PAGE_INITIAL_DELAY_MAX = float(os.getenv('SEARCH_PAGE_INITIAL_DELAY_MAX', '3.0'))

# Browser mode settings
HEADLESS_MODE = os.getenv('DEFAULT_HEADLESS', 'false').lower() == 'true'  # Set to True for headless mode (faster, less RAM, no visible window)
                       # Recommended: False for debugging, True for production/automated runs

# Timeout settings (in seconds)
PAGE_LOAD_TIMEOUT = 30  # Increased from 15s to allow for slow Noon loads
ELEMENT_WAIT_TIMEOUT = 10  # Increased from 3s for general elements
ELEMENT_WAIT_TIMEOUT_CRITICAL = 15  # Increased from 5s for search results
ELEMENT_WAIT_TIMEOUT_FAST = 0.5  # Keep fast for optional elements
SCROLL_PAUSE_TIME = 1.0  # Increased from 0.5s for stability

# Delays to avoid bot detection (in seconds) - OPTIMIZED FOR ROBUSTNESS
REQUEST_DELAY_MIN = 0.5  # Slightly increased
REQUEST_DELAY_MAX = 2.0  # Increased from 0.8s to vary patterns more
PRODUCT_DETAIL_DELAY = 1.0  # Increased from 0.5s
SCROLL_DELAY_MIN = 0.2  # Increased from 0.1s
SCROLL_DELAY_MAX = 0.5  # Increased from 0.3s

# CSS Selectors (using partial matching for dynamic class names)
SELECTORS = {
    # Search results page
    'product_links': 'a[href*="/p/"]',
    'product_card': 'a[class*="productBoxLink"], div[class*="productBox"]',
    
    # Product detail page
    'product_title': 'h1',
    'price_now': '[class*="priceNowText"], [class*="priceNow"]',
    'rating_value': 'div[class*="rating"] span, span[class*="rating"]',
    'reviews_count': '[class*="reviews"], [class*="rating"]',
    'breadcrumbs': 'nav[class*="breadcrumb"] a, [class*="Breadcrumb"] a',
    'seller_name': '[class*="soldBy"], [class*="SoldBy"]',
    'other_sellers_button': 'button:has-text("other seller")',
    'highlights': 'ul[class*="highlights"] li, div[class*="highlights"] li, [class*="description"]',
    'grade': 'td.SpecificationsTab-module-scss-module__xe5LJa__specName, [class*="condition"], [class*="grade"], [class*="quality"]',
    'express_delivery': 'div.VipPdpShippingEstimatorV2-module-scss-module__o-fWFa__fullfilmentBadgeCtr img, [class*="express"], [class*="delivery"], [class*="shipping"]',
    
    # Other sellers modal
    'modal_sellers': '[class*="offerCard"], [class*="sellerCard"], div[class*="offer"]',
    'modal_seller_name': '[class*="sellerName"], [class*="partner"] strong, strong',
    'modal_seller_price': '[class*="price"]',
    'modal_seller_rating': '[class*="rating"]',
    'close_modal': 'button[class*="close"], [aria-label="Close"], button[class*="Close"]',
}

# Output settings
OUTPUT_DIR = "output"
OUTPUT_FILENAME_PREFIX = "noon_scraper"

# Excel column headers
EXCEL_HEADERS = [
    "Search Keyword",
    "Category",
    "Title",
    "Description",
    "Price",
    "Rating",
    "Reviews",
    "Seller",
    "Grade",
    "Delivery",
    "Product URL",
    "Region",
    "Platform"
]

# Logging
LOG_FILE = "scraper.log"
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


# Pagination settings
MAX_SCROLLS = 10  # Increased to 10 - Capture ~100 products per keyword for better arbitrage coverage
LOAD_MORE_ENABLED = True  # Try to click "Load More" button if available
MAX_PRODUCTS_PER_KEYWORD = None

# Optional Chrome major version. Leave unset for auto-detection.
CHROME_VERSION_MAIN = os.getenv('CHROME_VERSION_MAIN', '').strip() or None

# Seller extraction settings
# SKIP_OTHER_SELLERS_MODAL removed - scraper now always checks for other sellers



# User-Agent Rotation (Anti-Bot) - Updated
USER_AGENTS = [
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    
    # Chrome on Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    
    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
    
    # Chrome on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
]
