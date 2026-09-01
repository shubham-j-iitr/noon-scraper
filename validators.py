"""
Data Validation Module
Validates scraped product data to detect failures
"""

import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProductDataValidator:
    """Validates scraped product data"""
    
    def __init__(self):
        """Initialize validator with metrics tracking"""
        self.validation_stats = {
            "total_validated": 0,
            "passed": 0,
            "failed": 0,
            "failures_by_field": {}
        }
    
    def validate_product_data(self, data, keyword=None):
        """
        Validate a single product data dictionary
        
        Args:
            data (dict): Product data to validate
            keyword (str): Search keyword (for logging)
        
        Returns:
            tuple: (is_valid, errors_list)
        """
        self.validation_stats["total_validated"] += 1
        errors = []
        
        # Validate Title
        if not self._validate_title(data.get("Title")):
            errors.append("Missing or invalid Title")
            self._increment_failure("Title")
        
        # Validate Price
        if not self._validate_price(data.get("Price")):
            errors.append("Missing or invalid Price")
            self._increment_failure("Price")
        
        # Validate Product URL
        if not self._validate_url(data.get("Product URL")):
            errors.append("Missing or invalid Product URL")
            self._increment_failure("Product URL")
        
        # Validate Seller (optional but recommended)
        if not data.get("Seller") or data.get("Seller") == "N/A":
            errors.append("Missing Seller information")
            self._increment_failure("Seller")
        
        # Check if this is a "Not Found" placeholder
        if data.get("Category") == "Not Found":
            # This is expected for keywords with no results, not a validation failure
            is_valid = True
        else:
            is_valid = len(errors) == 0
        
        if is_valid:
            self.validation_stats["passed"] += 1
        else:
            self.validation_stats["failed"] += 1
            logger.warning(f"Validation failed for product{f' (keyword: {keyword})' if keyword else ''}: {', '.join(errors)}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Invalid data: {data}")
        
        return is_valid, errors
    
    def _validate_title(self, title):
        """Validate product title"""
        if not title or not isinstance(title, str):
            return False
        
        # Title should be at least 5 characters
        if len(title.strip()) < 5:
            return False
        
        # Title shouldn't be placeholder text
        invalid_titles = ["n/a", "not found", "error", "none"]
        if title.lower().strip() in invalid_titles:
            return False
        
        return True
    
    def _validate_price(self, price):
        """Validate product price"""
        if price is None or price == "":
            return False
        
        # Try to convert to float
        try:
            # Remove currency symbols and formatting
            cleaned_price = str(price).replace(",", "").replace("AED", "").replace("SAR", "").strip()
            price_value = float(cleaned_price)
            
            # Price should be positive
            if price_value <= 0:
                return False
            
            # Price should be reasonable (not astronomical)
            if price_value > 1000000:  # 1 million AED/SAR seems like a reasonable max
                return False
            
            return True
        except (ValueError, TypeError):
            return False
    
    def _validate_url(self, url):
        """Validate product URL"""
        if not url or not isinstance(url, str):
            return False
        
        # Check if it's a valid URL
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False
            
            # Should be a noon.com URL
            if "noon.com" not in result.netloc.lower():
                logger.warning(f"URL is not from noon.com: {url}")
                # Still valid, just suspicious
            
            return True
        except Exception:
            return False
    
    def _increment_failure(self, field_name):
        """Track failures by field"""
        if field_name not in self.validation_stats["failures_by_field"]:
            self.validation_stats["failures_by_field"][field_name] = 0
        self.validation_stats["failures_by_field"][field_name] += 1
    
    def get_validation_report(self):
        """
        Generate validation statistics report
        
        Returns:
            dict: Validation statistics
        """
        stats = self.validation_stats.copy()
        
        # Calculate success rate
        total = stats["total_validated"]
        if total > 0:
            stats["success_rate"] = (stats["passed"] / total) * 100
        else:
            stats["success_rate"] = 0.0
        
        return stats
    
    def print_validation_report(self):
        """Print validation report to console"""
        stats = self.get_validation_report()
        
        print("\n" + "="*60)
        print("DATA VALIDATION REPORT")
        print("="*60)
        print(f"Total products validated: {stats['total_validated']}")
        print(f"Passed validation: {stats['passed']}")
        print(f"Failed validation: {stats['failed']}")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        
        if stats["failures_by_field"]:
            print(f"\nFailures by field:")
            for field, count in sorted(stats["failures_by_field"].items(), 
                                      key=lambda x: x[1], reverse=True):
                print(f"  - {field}: {count}")
        
        print("="*60 + "\n")
        
        # Log the report as well
        logger.info(f"Validation Report: {stats['passed']}/{stats['total_validated']} passed ({stats['success_rate']:.1f}%)")
    
    def reset_stats(self):
        """Reset validation statistics"""
        self.validation_stats = {
            "total_validated": 0,
            "passed": 0,
            "failed": 0,
            "failures_by_field": {}
        }


# Global validator instance
_validator = ProductDataValidator()


def validate_product_data(data, keyword=None):
    """
    Convenience function for validating product data
    
    Args:
        data (dict): Product data to validate
        keyword (str): Search keyword (for logging)
    
    Returns:
        tuple: (is_valid, errors_list)
    """
    return _validator.validate_product_data(data, keyword)


def get_validation_report():
    """Get validation statistics report"""
    return _validator.get_validation_report()


def print_validation_report():
    """Print validation report to console"""
    _validator.print_validation_report()


def reset_validation_stats():
    """Reset validation statistics"""
    _validator.reset_stats()
