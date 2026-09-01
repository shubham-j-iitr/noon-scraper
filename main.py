"""
Noon Web Scraper - Main Entry Point
Author: Tatenda Marimo
Description: Scrapes product listings from noon.com with multi-seller support
"""

import sys
from noon_scraper import NoonScraper
from excel_exporter import ExcelExporter
from checkpoint_manager import CheckpointManager
import logging
from tqdm import tqdm

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass  # If it fails, continue without UTF-8

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print application banner"""
    print("Noon Web Scraper v1.0")


def get_user_input():
    """
    Get search keywords from user or file
    
    Returns:
        list: List of keywords
    """
    import os
    
    # Check for keywords.txt
    if os.path.exists('keywords.txt'):
        try:
            with open('keywords.txt', 'r', encoding='utf-8') as f:
                file_keywords = [line.strip() for line in f if line.strip()]
            
            if file_keywords:
                print("\n" + "="*60)
                print("BULK LOAD DETECTED")
                print("="*60)
                print(f"\nFound 'keywords.txt' with {len(file_keywords)} keywords.")
                
                while True:
                    response = input("Do you want to load these keywords? (yes/no): ").strip().lower()
                    if response in ['yes', 'y']:
                        print(f"Loaded {len(file_keywords)} keywords from file.")
                        return file_keywords
                    elif response in ['no', 'n']:
                        break
        except Exception as e:
            logger.error(f"Error reading keywords.txt: {e}")
            print(f"Error reading keywords.txt: {e}")

    print("\n" + "="*60)
    print("KEYWORD INPUT")
    print("="*60)
    print("\nEnter search keywords (one per line)")
    print("Press Enter twice when done, or type 'done' to finish\n")
    
    keywords = []
    while True:
        keyword = input(f"Keyword {len(keywords) + 1}: ").strip()
        
        if keyword.lower() == 'done' or keyword == '':
            if keywords:
                break
            else:
                print("Please enter at least one keyword!")
                continue
        
        keywords.append(keyword)
    
    return keywords


def get_max_products():
    """
    Ask user for maximum products per keyword
    
    Returns:
        int or None: Max products or None for all
    """
    print("\n" + "="*60)
    print("PRODUCT LIMIT")
    print("="*60)
    
    while True:
        response = input("\nLimit products per keyword? (Enter number or press Enter for all): ").strip()
        
        if response == '':
            return None
        
        try:
            max_products = int(response)
            if max_products > 0:
                return max_products
            else:
                print("Please enter a positive number!")
        except ValueError:
            print("Invalid input! Please enter a number or press Enter.")


def get_headless_mode():
    """
    Ask user if they want to run in headless mode
    
    Returns:
        bool: True for headless mode, False for visible browser
    """
    print("\n" + "="*60)
    print("BROWSER MODE")
    print("="*60)
    print("\nRun browser in headless mode?")
    print("  YES - Faster, uses less RAM, no visible window (recommended for production)")
    print("  NO  - Visible browser, easier to debug (recommended for testing)")
    
    while True:
        response = input("\nHeadless mode? (yes/no, default: yes): ").strip().lower()
        
        if response in ['yes', 'y', '']:
            print("[OK] Headless mode enabled - browser will run invisibly")
            return True
        elif response in ['no', 'n']:
            print("[OK] Visible mode - you'll see the browser window")
            return False
        else:
            print("Invalid choice! Please enter 'yes' or 'no'")


def get_region():
    """
    Ask user to select region
    
    Returns:
        str or list: Selected region code ('uae', 'ksa', or ['uae', 'ksa'] for both)
    """
    print("\n" + "="*60)
    print("REGION SELECTION")
    print("="*60)
    print("\nSelect Noon region to scrape:")
    print("  1. UAE (United Arab Emirates)")
    print("  2. KSA (Saudi Arabia)")
    print("  3. Both (UAE + KSA)")
    
    while True:
        response = input("\nEnter region (1, 2, or 3): ").strip()
        
        if response == '1':
            return 'uae'
        elif response == '2':
            return 'ksa'
        elif response == '3':
            return ['uae', 'ksa']
        else:
            print("Invalid choice! Please enter 1, 2, or 3.")

def check_for_existing_checkpoint():
    """
    Check for existing checkpoints and offer to resume
    
    Returns:
        tuple: (checkpoint_manager, should_resume, checkpoint_data)
    """
    checkpoint_mgr = CheckpointManager()
    latest_checkpoint = checkpoint_mgr.load_latest_checkpoint()
    
    if latest_checkpoint and latest_checkpoint.get('status') == 'in_progress':
        print("\n" + "="*60)
        print("PREVIOUS SESSION DETECTED")
        print("="*60)
        
        completed = checkpoint_mgr.get_all_completed_keywords()
        scraped = checkpoint_mgr.get_all_scraped_data()
        total = latest_checkpoint.get('total_keywords', 0)
        started = latest_checkpoint.get('started_at', 'Unknown')
        
        print(f"\nFound incomplete scraping session from {started}")
        print(f"Progress: {len(completed)}/{total} keywords completed")
        print(f"Data scraped: {len(scraped)} rows")
        
        if completed:
            print(f"\nCompleted keywords:")
            for kw in completed[:5]:  # Show first 5
                print(f"  * {kw}")
            if len(completed) > 5:
                print(f"  ... and {len(completed) - 5} more")
        
        print("\n" + "="*60)
        
        while True:
            response = input("\nResume from checkpoint? (yes/no): ").strip().lower()
            if response in ['yes', 'y']:
                print("[OK] Resuming from checkpoint...")
                return checkpoint_mgr, True, latest_checkpoint
            elif response in ['no', 'n']:
                print("[OK] Starting fresh session. Clearing old checkpoints...")
                checkpoint_mgr.clear_all_checkpoints()
                return checkpoint_mgr, False, None
            else:
                print("Please enter 'yes' or 'no'")
    
    # Even if no active in-progress checkpoint exists, clear any stale completed checkpoints on a fresh start
    checkpoint_mgr.clear_all_checkpoints()
    return checkpoint_mgr, False, None


def confirm_scrape(keywords, max_products, region='uae'):
    """
    Show summary and confirm before scraping
    
    Args:
        keywords (list): List of keywords
        max_products (int or None): Max products limit
        region (str or list): Region code or list of region codes
        
    Returns:
        bool: True if confirmed
    """
    print(f"\nSummary: {len(keywords)} keywords, Max {max_products or 'All'} products")
    print(f"Region: {region}")
    
    estimated_seconds = len(keywords) * (max_products or 20) * 4
    print(f"Est. Time: ~{estimated_seconds // 60}m {estimated_seconds % 60}s")
    
    while True:
        response = input("\nProceed with scraping? (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("Please enter 'yes' or 'no'")


def main():
    """Main application flow"""
    
    # Print banner
    print_banner()
    
    checkpoint = None
    
    try:
        # Check for existing checkpoint
        checkpoint, should_resume, checkpoint_data = check_for_existing_checkpoint()
        
        # Get user input or use checkpoint data
        if should_resume:
            # Load from checkpoint
            all_keywords = checkpoint_data.get('all_keywords', [])
            remaining_keywords = checkpoint.get_remaining_keywords(all_keywords)
            existing_data = checkpoint.get_scraped_data()
            max_products = checkpoint_data.get('max_products')
            headless = checkpoint_data.get('headless', False)
            region = checkpoint_data.get('region', 'uae')
            
            print(f"\n[OK] Resuming with {len(remaining_keywords)} remaining keywords")
            keywords = remaining_keywords
        else:
            # Fresh start - get user input
            keywords = get_user_input()
            max_products = get_max_products()
            headless = get_headless_mode()
            region = get_region()
            existing_data = []
            
            # Confirm before proceeding
            if not confirm_scrape(keywords, max_products, region):
                print("\nScraping cancelled by user")
                return
            
            # Start new checkpoint session
            from datetime import datetime
            session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
            checkpoint.start_new_checkpoint(session_name)
            checkpoint.set_total_keywords(len(keywords))
            
            # Save session config to checkpoint
            checkpoint.current_checkpoint['all_keywords'] = keywords
            checkpoint.current_checkpoint['max_products'] = max_products
            checkpoint.current_checkpoint['headless'] = headless
            checkpoint.current_checkpoint['region'] = region
            checkpoint._save_checkpoint()
        
        # Handle multi-region scraping with TRUE MULTIPROCESSING
        regions_to_scrape = region if isinstance(region, list) else [region]
        
        print("\n" + "="*60)
        mode_text = "HEADLESS MODE" if headless else "VISIBLE MODE"
        print(f"MULTIPROCESSING MODE - {mode_text}")
        print("="*60)
        print(f"\nRegions to scrape: {', '.join([r.upper() for r in regions_to_scrape])}")
        print(f"Total keywords: {len(keywords)}")
        print(f"\n[INFO] Using TRUE PARALLEL PROCESSING (separate processes per region)")
        print("   This will ~50% faster than sequential!\n")
        
        # Import multiprocessing worker
        from multiprocessing_worker import scrape_region_worker
        from concurrent.futures import ProcessPoolExecutor, as_completed
        
        # Create process pool (max 2 workers for UAE + KSA)
        max_workers = len(regions_to_scrape)
        
        # Submit jobs to process pool
        futures = {}
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for idx, region_code in enumerate(regions_to_scrape):
                print(f"   [START] Launching {region_code.upper()} process...")
                future = executor.submit(
                    scrape_region_worker,
                    keywords,
                    region_code,
                    headless,
                    max_products,
                    checkpoint.current_checkpoint['session_name']
                )
                futures[future] = region_code
                
                # Stagger the next process launch to prevent browser startup race conditions
                if idx < len(regions_to_scrape) - 1:
                    import time
                    print("   [INFO] Waiting 10 seconds before launching next process to avoid browser initialization conflicts...")
                    time.sleep(10)
            
            print(f"\n[SUCCESS] All {len(regions_to_scrape)} processes launched!")
            print("   Scraping in parallel... this will take ~1.7 hours for 121 keywords\n")
            
            # Collect results as they complete
            all_data = []
            completed_regions = 0
            
            for future in as_completed(futures):
                region_code = futures[future]
                try:
                    region_data = future.result()
                    all_data.extend(region_data)
                    completed_regions += 1
                    
                    print(f"\n{'='*60}")
                    print(f"[SUCCESS] {region_code.upper()} PROCESS COMPLETED!")
                    print(f"{'='*60}")
                    print(f"   Items scraped: {len(region_data)}")
                    print(f"   Progress: {completed_regions}/{len(regions_to_scrape)} regions done")
                    print(f"{'='*60}\n")
                    
                except Exception as e:
                    logger.error(f"Region {region_code} process failed: {e}", exc_info=True)
                    print(f"\n[ERROR] {region_code.upper()} PROCESS FAILED: {e}\n")
        
        print(f"\n{'='*60}")
        print("[DONE] ALL PROCESSES COMPLETED!")
        print(f"{'='*60}")
        print(f"Total items scraped: {len(all_data)}")
        print(f"{'='*60}\n")
        
        # Mark checkpoint as completed
        checkpoint.mark_completed()
        
        # Check if any data was scraped
        if not all_data:
            print("\nNo data was scraped from any region. Please check the logs for errors.")
            checkpoint.mark_failed("No data scraped")
            return
        
        # Export to Excel
        print("\n" + "="*60)
        print("EXPORTING TO EXCEL")
        print("="*60 + "\n")
        
        exporter = ExcelExporter()
        
        # Use first keyword for filename if only one keyword (use all_keywords from checkpoint if resuming)
        all_keywords_list = checkpoint.current_checkpoint.get('all_keywords', keywords)
        filename_keyword = all_keywords_list[0] if len(all_keywords_list) == 1 else None
        filepath = exporter.export_to_excel(all_data, keyword=filename_keyword)
        
        # Success message
        print("\n" + "="*60)
        print("SCRAPING COMPLETED SUCCESSFULLY!")
        print("="*60)
        print(f"\nTotal products scraped: {len(all_data)}")
        if len(regions_to_scrape) > 1:
            print(f"Regions scraped: {', '.join([r.upper() for r in regions_to_scrape])}")
        print(f"Excel file saved: {filepath}")
        print(f"\nTip: Open the Excel file to view all scraped data")
        print("="*60 + "\n")
        
        # Cleanup old checkpoints (keep last 5)
        checkpoint.cleanup_old_checkpoints(keep_last_n=5)
        
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user (Ctrl+C)")
        if checkpoint:
            checkpoint.mark_failed("Interrupted by user")
            print("\n[INFO] Progress saved! Run the scraper again to resume from checkpoint.")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        if checkpoint:
            checkpoint.mark_failed(str(e))
        print(f"\nAn error occurred: {str(e)}")
        print("Check scraper.log for details")
        if checkpoint:
            print("[INFO] Progress saved! Run the scraper again to resume from checkpoint.")
        sys.exit(1)


if __name__ == "__main__":
    main()
