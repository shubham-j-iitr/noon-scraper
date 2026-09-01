"""
Checkpoint Manager Module
Handles saving and loading scraping progress for resume functionality
"""

import json
import os
from datetime import datetime
import logging
from filelock import FileLock

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages scraping checkpoints for resume capability"""
    
    def __init__(self, checkpoint_dir="checkpoints"):
        """
        Initialize checkpoint manager
        
        Args:
            checkpoint_dir (str): Directory to store checkpoint files
        """
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_file = None
        self.current_checkpoint = None
        
        # Create checkpoint directory if it doesn't exist
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
            logger.info(f"Created checkpoint directory: {checkpoint_dir}")
    
    def start_new_checkpoint(self, session_name=None):
        """
        Start a new checkpoint session
        
        Args:
            session_name (str): Optional session name, defaults to timestamp
        
        Returns:
            str: Checkpoint file path
        """
        if session_name is None:
            session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.checkpoint_file = os.path.join(self.checkpoint_dir, f"checkpoint_{session_name}.json")
        
        self.current_checkpoint = {
            "session_name": session_name,
            "started_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "completed_keywords": [],
            "scraped_data": [],
            "total_keywords": 0,
            "current_region": None,
            "status": "in_progress",
            # Multiprocessing support
            "region_progress": {"uae": [], "ksa": []},
            "region_data": {"uae": [], "ksa": []}
        }
        
        self._save_checkpoint()
        logger.info(f"Started new checkpoint session: {session_name}")
        return self.checkpoint_file
    
    def save_keyword_progress(self, keyword, scraped_data, region=None):
        """
        Save progress after completing a keyword
        
        Args:
            keyword (str): Completed keyword
            scraped_data (list): Data scraped for this keyword
            region (str): Current region being scraped
        """
        if self.current_checkpoint is None:
            logger.warning("No active checkpoint session")
            return
        
        # Add to completed keywords
        if keyword not in self.current_checkpoint["completed_keywords"]:
            self.current_checkpoint["completed_keywords"].append(keyword)
        
        # Add scraped data
        self.current_checkpoint["scraped_data"].extend(scraped_data)
        
        # Update metadata
        self.current_checkpoint["last_updated"] = datetime.now().isoformat()
        if region:
            self.current_checkpoint["current_region"] = region
        
        self._save_checkpoint()
        
        progress = len(self.current_checkpoint["completed_keywords"])
        total = self.current_checkpoint.get("total_keywords", 0)
        logger.info(f"Checkpoint saved: {keyword} ({progress}/{total} keywords completed)")
    
    def mark_completed(self):
        """Mark checkpoint as completed"""
        # Reload latest state from disk to include worker updates
        if self.checkpoint_file and os.path.exists(self.checkpoint_file):
            try:
                self.load_checkpoint(os.path.basename(self.checkpoint_file))
            except Exception as e:
                logger.error(f"Failed to reload checkpoint before completion: {e}")

        if self.current_checkpoint:
            self.current_checkpoint["status"] = "completed"
            self.current_checkpoint["completed_at"] = datetime.now().isoformat()
            self._save_checkpoint()
            logger.info("Checkpoint marked as completed")
    
    def mark_failed(self, error_message=None):
        """Mark checkpoint as failed"""
        # Reload latest state from disk to include worker updates
        if self.checkpoint_file and os.path.exists(self.checkpoint_file):
            try:
                self.load_checkpoint(os.path.basename(self.checkpoint_file))
            except Exception as e:
                logger.error(f"Failed to reload checkpoint before failure: {e}")

        if self.current_checkpoint:
            self.current_checkpoint["status"] = "failed"
            self.current_checkpoint["failed_at"] = datetime.now().isoformat()
            if error_message:
                self.current_checkpoint["error"] = str(error_message)
            self._save_checkpoint()
            logger.error(f"Checkpoint marked as failed: {error_message}")
    
    def _save_checkpoint(self):
        """Save checkpoint to file with file locking for process safety"""
        if self.checkpoint_file and self.current_checkpoint:
            lock_file = self.checkpoint_file + '.lock'
            lock = FileLock(lock_file, timeout=10)
            try:
                with lock:
                    with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                        json.dump(self.current_checkpoint, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")
    
    def load_latest_checkpoint(self):
        """
        Load the most recent checkpoint file
        
        Returns:
            dict or None: Checkpoint data if found, None otherwise
        """
        checkpoint_files = [f for f in os.listdir(self.checkpoint_dir) 
                          if f.startswith("checkpoint_") and f.endswith(".json")]
        
        if not checkpoint_files:
            logger.info("No checkpoint files found")
            return None
        
        # Get most recent checkpoint
        latest_file = max(checkpoint_files, 
                         key=lambda f: os.path.getctime(os.path.join(self.checkpoint_dir, f)))
        
        return self.load_checkpoint(latest_file)
    
    def load_checkpoint(self, filename):
        """
        Load a specific checkpoint file
        
        Args:
            filename (str): Checkpoint filename
        
        Returns:
            dict or None: Checkpoint data if successful, None otherwise
        """
        filepath = os.path.join(self.checkpoint_dir, filename) if not os.path.isabs(filename) else filename
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.current_checkpoint = json.load(f)
                self.checkpoint_file = filepath
                
                logger.info(f"Loaded checkpoint: {filename}")
                logger.info(f"  - Started: {self.current_checkpoint.get('started_at')}")
                logger.info(f"  - Status: {self.current_checkpoint.get('status')}")
                logger.info(f"  - Completed keywords: {len(self.current_checkpoint.get('completed_keywords', []))}")
                
                return self.current_checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint {filename}: {e}")
            return None
    
    def get_all_completed_keywords(self):
        """
        Get all completed keywords aggregated from all regions
        
        Returns:
            list: List of unique completed keywords
        """
        if self.current_checkpoint is None:
            return []
            
        completed = set(self.current_checkpoint.get("completed_keywords", []))
        
        # Add region-specific progress
        region_progress = self.current_checkpoint.get("region_progress", {})
        for region_keywords in region_progress.values():
            completed.update(region_keywords)
            
        return list(completed)

    def get_remaining_keywords(self, all_keywords):
        """
        Get list of keywords that haven't been completed yet
        
        Args:
            all_keywords (list): Complete list of keywords
        
        Returns:
            list: Keywords that still need to be scraped
        """
        completed = set(self.get_all_completed_keywords())
        remaining = [kw for kw in all_keywords if kw not in completed]
        
        logger.info(f"Remaining keywords: {len(remaining)} out of {len(all_keywords)}")
        return remaining

    def get_all_scraped_data(self):
        """
        Get all scraped data aggregated from all regions
        
        Returns:
            list: All scraped data
        """
        if self.current_checkpoint is None:
            return []
            
        all_data = list(self.current_checkpoint.get("scraped_data", []))
        
        # Add region-specific data
        region_data = self.current_checkpoint.get("region_data", {})
        for products in region_data.values():
            all_data.extend(products)
            
        return all_data

    def get_scraped_data(self):
        """
        Get all scraped data from checkpoint
        
        Returns:
            list: All scraped data
        """
        return self.get_all_scraped_data()
    
    def set_total_keywords(self, total):
        """Set total number of keywords for progress tracking"""
        if self.current_checkpoint:
            self.current_checkpoint["total_keywords"] = total
            self._save_checkpoint()
    
    def cleanup_old_checkpoints(self, keep_last_n=5):
        """
        Remove old checkpoint files, keeping only the most recent N
        
        Args:
            keep_last_n (int): Number of recent checkpoints to keep
        """
        checkpoint_files = [f for f in os.listdir(self.checkpoint_dir) 
                          if f.startswith("checkpoint_") and f.endswith(".json")]
        
        if len(checkpoint_files) <= keep_last_n:
            return
        
        # Sort by creation time, oldest first
        sorted_files = sorted(checkpoint_files, 
                            key=lambda f: os.path.getctime(os.path.join(self.checkpoint_dir, f)))
        
        # Delete oldest files
        files_to_delete = sorted_files[:-keep_last_n]
        for filename in files_to_delete:
            try:
                filepath = os.path.join(self.checkpoint_dir, filename)
                os.remove(filepath)
                logger.info(f"Cleaned up old checkpoint: {filename}")
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint {filename}: {e}")

    def clear_all_checkpoints(self):
        """Delete all existing checkpoints to start completely fresh."""
        checkpoint_files = [f for f in os.listdir(self.checkpoint_dir) 
                          if f.startswith("checkpoint_") and f.endswith(".json") or f.endswith(".json.lock")]
        
        deleted_count = 0
        for filename in checkpoint_files:
            try:
                filepath = os.path.join(self.checkpoint_dir, filename)
                os.remove(filepath)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} old checkpoint files")
            return True
        return False
        
    # ============================================================================
    # MULTIPROCESSING METHODS
    # ============================================================================
    
    def save_region_keyword_progress(self, session_name, region, keyword, scraped_data):
        """
        Save progress for a specific region (process-safe)
        
        Args:
            session_name (str): Session name
            region (str): Region code ('uae' or 'ksa')
            keyword (str): Completed keyword
            scraped_data (list): Data scraped for this keyword
        """
        checkpoint_file = os.path.join(self.checkpoint_dir, f"checkpoint_{session_name}.json")
        lock_file = checkpoint_file + '.lock'
        lock = FileLock(lock_file, timeout=10)
        
        try:
            with lock:
                # Load current checkpoint
                if os.path.exists(checkpoint_file):
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        checkpoint_data = json.load(f)
                else:
                    logger.error(f"Checkpoint file not found: {checkpoint_file}")
                    return
                
                # Initialize region tracking if needed
                if "region_progress" not in checkpoint_data:
                    checkpoint_data["region_progress"] = {"uae": [], "ksa": []}
                if "region_data" not in checkpoint_data:
                    checkpoint_data["region_data"] = {"uae": [], "ksa": []}
                
                # Add to region-specific progress
                if keyword not in checkpoint_data["region_progress"][region]:
                    checkpoint_data["region_progress"][region].append(keyword)
                
                # Add scraped data for this region
                checkpoint_data["region_data"][region].extend(scraped_data)
                
                # Update last updated time
                checkpoint_data["last_updated"] = datetime.now().isoformat()
                
                # Save back
                with open(checkpoint_file, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
                
                progress = len(checkpoint_data["region_progress"][region])
                logger.info(f"[{region.upper()}] Checkpoint saved: {keyword} ({progress} keywords completed)")
                
        except Exception as e:
            logger.error(f"Failed to save region progress: {e}")
    
    def get_remaining_keywords_for_region(self, session_name, region, all_keywords):
        """
        Get list of keywords not yet completed for a specific region
        
        Args:
            session_name (str): Session name
            region (str): Region code ('uae' or 'ksa')
            all_keywords (list): Complete list of keywords
            
        Returns:
            list: Keywords that still need to be scraped for this region
        """
        checkpoint_file = os.path.join(self.checkpoint_dir, f"checkpoint_{session_name}.json")
        
        if not os.path.exists(checkpoint_file):
            logger.info(f"No checkpoint found for {session_name}, processing all keywords")
            return all_keywords
        
        lock_file = checkpoint_file + '.lock'
        lock = FileLock(lock_file, timeout=10)
        
        try:
            with lock:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                
                # Get completed keywords for this region
                region_progress = checkpoint_data.get("region_progress", {}).get(region, [])
                completed = set(region_progress)
                remaining = [kw for kw in all_keywords if kw not in completed]
                
                logger.info(f"[{region.upper()}] Remaining keywords: {len(remaining)} out of {len(all_keywords)}")
                return remaining
                
        except Exception as e:
            logger.error(f"Failed to load region progress: {e}")
            return all_keywords
    
    def get_scraped_data_for_region(self, session_name, region):
        """
        Get all scraped data for a specific region from checkpoint
        
        Args:
            session_name (str): Session name
            region (str): Region code ('uae' or 'ksa')
            
        Returns:
            list: All scraped data for this region
        """
        checkpoint_file = os.path.join(self.checkpoint_dir, f"checkpoint_{session_name}.json")
        
        if not os.path.exists(checkpoint_file):
            return []
        
        lock_file = checkpoint_file + '.lock'
        lock = FileLock(lock_file, timeout=10)
        
        try:
            with lock:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                
                region_data = checkpoint_data.get("region_data", {}).get(region, [])
                logger.info(f"[{region.upper()}] Loaded {len(region_data)} items from checkpoint")
                return region_data
                
        except Exception as e:
            logger.error(f"Failed to load region data: {e}")
            return []
