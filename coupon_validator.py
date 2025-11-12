#!/usr/bin/env python3
"""
FunderPro Coupon Validation Module
Validates coupon codes against FunderPro's CRM API with retry logic and caching
"""

import os
import time
import requests
from urllib.parse import urlencode
from datetime import datetime, timedelta
import threading

# FunderPro API configuration
FUNDERPRO_API_BASE = "https://api-ftp.funderpro.com/discount"
FUNDERPRO_PRODUCT_ID = os.environ.get('FUNDERPRO_PRODUCT_ID')

if not FUNDERPRO_PRODUCT_ID:
    raise ValueError(
        "FUNDERPRO_PRODUCT_ID environment variable must be set. "
        "Please add it to your .env file."
    )

# Thread-safe in-memory cache for validated coupons (TTL: 5 minutes)
_coupon_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 300

# Shared lock for telegram_bot.py's coupon_cache (exported for thread-safe access)
coupon_cache_lock = threading.Lock()


def _get_cached_result(coupon_code):
    """Check if we have a recent valid result for this coupon (thread-safe)."""
    key = coupon_code.upper()
    with _cache_lock:
        if key in _coupon_cache:
            result, timestamp = _coupon_cache[key]
            age = (datetime.now() - timestamp).total_seconds()
            if age < CACHE_TTL_SECONDS:
                print(f"[COUPON] ✅ Cache hit for '{coupon_code}' (age: {age:.1f}s)")
                return result
            else:
                # Expired, remove from cache
                del _coupon_cache[key]
    return None


def _cache_result(coupon_code, result):
    """Cache a successful validation result (thread-safe)."""
    if result['valid']:
        key = coupon_code.upper()
        with _cache_lock:
            _coupon_cache[key] = (result, datetime.now())
        print(f"[COUPON] 💾 Cached validation for '{coupon_code}'")


def validate_coupon(coupon_code, timeout=10, max_retries=3):
    """
    Validate a coupon code against FunderPro's CRM API with retry logic.
    
    Args:
        coupon_code (str): The coupon code to validate (e.g., "alpha", "SAVE20")
        timeout (int): Request timeout in seconds (default: 10)
        max_retries (int): Maximum retry attempts for transient errors (default: 3)
    
    Returns:
        dict: Validation result with keys:
            - valid (bool): True if coupon is active and valid
            - message (str): Human-readable message
            - status_code (int): HTTP status code from API
    
    Example:
        result = validate_coupon("alpha")
        if result['valid']:
            print("Coupon is valid!")
        else:
            print(f"Invalid: {result['message']}")
    """
    if not coupon_code or not coupon_code.strip():
        return {
            'valid': False,
            'message': 'Coupon code cannot be empty',
            'status_code': 400
        }
    
    coupon_code = coupon_code.strip()
    
    # Check cache first
    cached = _get_cached_result(coupon_code)
    if cached:
        return cached
    
    # Build the API URL
    params = {
        'coupons[]': coupon_code,
        'productIds': FUNDERPRO_PRODUCT_ID
    }
    url = f"{FUNDERPRO_API_BASE}?{urlencode(params)}"
    
    # Retry loop for transient errors
    for attempt in range(max_retries):
        try:
            print(f"[COUPON] Validating '{coupon_code}' (attempt {attempt + 1}/{max_retries})...")
            response = requests.get(url, timeout=timeout)
            
            # Log response details
            print(f"[COUPON] API response: status={response.status_code}, body_length={len(response.text)}")
            
            # 200 OK means coupon is valid
            if response.status_code == 200:
                result = {
                    'valid': True,
                    'message': 'Coupon is active and valid',
                    'status_code': 200
                }
                _cache_result(coupon_code, result)
                print(f"[COUPON] ✅ '{coupon_code}' is VALID")
                return result
            
            # 404 or 422 means genuinely invalid coupon - don't retry
            elif response.status_code in [404, 422]:
                result = {
                    'valid': False,
                    'message': 'This is not a valid FunderPro coupon code - to request a coupon code, please reach out to affiliates@funderpro.com',
                    'status_code': response.status_code
                }
                print(f"[COUPON] ❌ '{coupon_code}' is INVALID (status {response.status_code})")
                return result
            
            # Rate limit or server error - retry with backoff
            elif response.status_code in [429, 500, 502, 503, 504]:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    print(f"[COUPON] ⚠️ Transient error {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed
                    return {
                        'valid': False,
                        'message': 'FunderPro API is temporarily unavailable. Please try again in a moment.',
                        'status_code': response.status_code
                    }
            
            # Other HTTP errors - treat as invalid but log details
            else:
                print(f"[COUPON] ⚠️ Unexpected status {response.status_code}: {response.text[:200]}")
                return {
                    'valid': False,
                    'message': 'This is not a valid FunderPro coupon code - to request a coupon code, please reach out to affiliates@funderpro.com',
                    'status_code': response.status_code
                }
        
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                print(f"[COUPON] ⏱️ Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"[COUPON] ❌ Timeout after {max_retries} attempts")
                return {
                    'valid': False,
                    'message': 'Coupon validation timed out. Please try again.',
                    'status_code': 0
                }
        
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                print(f"[COUPON] 🔌 Connection error, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"[COUPON] ❌ Connection error after {max_retries} attempts")
                return {
                    'valid': False,
                    'message': 'Unable to connect to FunderPro API. Please try again.',
                    'status_code': 0
                }
        
        except Exception as e:
            print(f"[COUPON] ❌ Unexpected error: {e}")
            return {
                'valid': False,
                'message': 'An error occurred while validating the coupon. Please try again.',
                'status_code': 0
            }
    
    # Should never reach here, but just in case
    return {
        'valid': False,
        'message': 'Validation failed after multiple retries.',
        'status_code': 0
    }


def validate_coupon_simple(coupon_code):
    """
    Simplified validation that returns only True/False.
    Useful for quick checks without detailed error messages.
    
    Args:
        coupon_code (str): The coupon code to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    result = validate_coupon(coupon_code)
    return result['valid']


if __name__ == "__main__":
    # Test the validator
    print("Testing FunderPro Coupon Validator\n")
    
    test_codes = [
        "alpha",  # Valid test coupon
        "alpha",  # Should hit cache
        "INVALID123",  # Should fail
        "",  # Empty string
    ]
    
    for code in test_codes:
        print(f"\nTesting: '{code}'")
        result = validate_coupon(code)
        print(f"  Valid: {result['valid']}")
        print(f"  Message: {result['message']}")
        print(f"  Status: {result['status_code']}")
