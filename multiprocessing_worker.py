"""
Multiprocessing worker module for parallel scraping
Provides picklable worker function for ProcessPoolExecutor
"""

import logging
from noon_scraper import NoonScraper
from checkpoint_manager import CheckpointManager

# Configure logging for multiprocessing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Process %(process)d] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def scrape_region_worker(keywords, region, headless, max_products, session_name):
    """
    Worker function for multiprocessing - scrapes all keywords for one region
    
    This function is designed to be pickled and run in a separate process.
    Each process gets its own browser instance and scrapes independently.
    
    Args:
        keywords (list): List of keywords to scrape
        region (str): Region code ('uae' or 'ksa')
        headless (bool): Run browser in headless mode
        max_products (int): Maximum products per keyword
        session_name (str): Checkpoint session name
        
    Returns:
        list: All scraped product data for this region
    """
    logger.info(f"Worker started for region: {region.upper()}")
    logger.info(f"Keywords to process: {len(keywords)}")
    
    scraper = None
    checkpoint = CheckpointManager()
    
    # Initialize all_data with existing data from checkpoint to ensure full export
    all_data = checkpoint.get_scraped_data_for_region(session_name, region)
    
    try:
        # Initialize scraper for this region
        import time
        logger.info(f"Initializing browser for {region.upper()}...")
        scraper = NoonScraper(headless=headless, region=region)
        
        init_retries = 3
        for attempt in range(1, init_retries + 1):
            try:
                scraper._init_driver()
                break
            except Exception as init_err:
                logger.error(f"[{region.upper()}] Browser initialization failed on attempt {attempt}/{init_retries}: {init_err}")
                if attempt < init_retries:
                    logger.info(f"[{region.upper()}] Waiting 5 seconds before retrying...")
                    time.sleep(5)
                else:
                    raise Exception(f"Failed to initialize browser after {init_retries} attempts: {init_err}")
                    
        logger.info(f"Browser ready for {region.upper()}")
        
        # Get remaining keywords for this region from checkpoint
        remaining_keywords = checkpoint.get_remaining_keywords_for_region(
            session_name, 
            region, 
            keywords
        )
        
        if not remaining_keywords:
            logger.info(f"No remaining keywords for {region.upper()} - already completed!")
            # Load existing data from checkpoint
            existing_data = checkpoint.get_scraped_data_for_region(session_name, region)
            return existing_data
        
        # Load existing data to populate seen_urls for de-duplication
        existing_data = checkpoint.get_scraped_data_for_region(session_name, region)
        seen_urls = set()
        
        if existing_data:
            logger.info(f"[{region.upper()}] Loading existing data for de-duplication...")
            for item in existing_data:
                url = item.get('Product URL')
                if url:
                    seen_urls.add(url)
            logger.info(f"[{region.upper()}] Loaded {len(seen_urls)} unique URLs to skip")
        
        logger.info(f"Processing {len(remaining_keywords)} keywords for {region.upper()}")
        
        # Process each keyword
        for idx, keyword in enumerate(remaining_keywords, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"[{region.upper()}] Keyword {idx}/{len(remaining_keywords)}: '{keyword}'")
            logger.info(f"{'='*60}\n")
            
            keyword_data = None
            max_retries = 3
            
            for attempt in range(1, max_retries + 1):
                try:
                    # Pre-scrape health check: restart browser if session is dead
                    if not scraper.is_session_valid():
                        logger.warning(f"[{region.upper()}] Browser session invalid before '{keyword}' (attempt {attempt}), restarting...")
                        scraper.restart_driver()
                    
                    # Scrape keyword
                    keyword_data = scraper.scrape_search_results(keyword, max_products, seen_urls)
                    break  # Success — exit retry loop
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    logger.error(f"[{region.upper()}] Attempt {attempt}/{max_retries} failed for '{keyword}': {e}")
                    
                    if 'invalid session' in error_msg or 'session not created' in error_msg or 'no such session' in error_msg:
                        # Browser crashed — restart and retry
                        logger.warning(f"[{region.upper()}] Browser crash detected, restarting for retry...")
                        try:
                            scraper.restart_driver()
                        except Exception as restart_err:
                            logger.error(f"[{region.upper()}] Failed to restart browser: {restart_err}")
                            if attempt == max_retries:
                                break
                    elif attempt == max_retries:
                        # Non-crash error on last attempt — give up on this keyword
                        logger.error(f"[{region.upper()}] All {max_retries} attempts failed for '{keyword}'")
                        break
                    else:
                        # Non-crash error — still retry but with a short pause
                        import time
                        time.sleep(2)
            
            if keyword_data:
                logger.info(f"[{region.upper()}] Found {len(keyword_data)} items for '{keyword}'")
                all_data.extend(keyword_data)
                
                # Save progress to checkpoint (process-safe)
                checkpoint.save_region_keyword_progress(
                    session_name, 
                    region, 
                    keyword, 
                    keyword_data
                )
            else:
                logger.warning(f"[{region.upper()}] No products found for '{keyword}'")
                # Save placeholder data
                placeholder = scraper._create_not_found_row(keyword)
                placeholder['Region'] = scraper.REGIONS[region]['name']
                all_data.append(placeholder)
                
                checkpoint.save_region_keyword_progress(
                    session_name, 
                    region, 
                    keyword, 
                    [placeholder]
                )
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[{region.upper()}] Worker completed!")
        logger.info(f"Total items scraped: {len(all_data)}")
        logger.info(f"{'='*60}\n")
        
        return all_data
        
    except Exception as e:
        logger.error(f"[{region.upper()}] Worker failed: {e}", exc_info=True)
        return all_data  # Return whatever was scraped so far
        
    finally:
        # Clean up browser
        if scraper and scraper.driver:
            try:
                scraper.driver.quit()
                logger.info(f"[{region.upper()}] Browser closed")
            except:
                pass
