#!/usr/bin/env python3
"""
FunderPro Coupon Validation Module
Validates coupon codes against FunderPro's CRM API
"""

import os
import requests
from urllib.parse import urlencode

# FunderPro API configuration
FUNDERPRO_API_BASE = "https://api-ftp.funderpro.com/discount"
FUNDERPRO_PRODUCT_ID = os.environ.get('FUNDERPRO_PRODUCT_ID')

if not FUNDERPRO_PRODUCT_ID:
    raise ValueError(
        "FUNDERPRO_PRODUCT_ID environment variable must be set. "
        "Please add it to your .env file."
    )

def validate_coupon(coupon_code, timeout=5):
    """
    Validate a coupon code against FunderPro's CRM API.
    
    Args:
        coupon_code (str): The coupon code to validate (e.g., "alpha", "SAVE20")
        timeout (int): Request timeout in seconds (default: 5)
    
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
    
    try:
        # Build the API URL with query parameters
        params = {
            'coupons[]': coupon_code,
            'productIds': FUNDERPRO_PRODUCT_ID
        }
        url = f"{FUNDERPRO_API_BASE}?{urlencode(params)}"
        
        # Make GET request to FunderPro API
        response = requests.get(url, timeout=timeout)
        
        # 200 OK means coupon is valid
        if response.status_code == 200:
            return {
                'valid': True,
                'message': 'Coupon is active and valid',
                'status_code': 200
            }
        
        # Any non-200 status means coupon is invalid or not active
        else:
            return {
                'valid': False,
                'message': 'This is not a valid FunderPro coupon code - to request a coupon code, please reach out to affiliates@funderpro.com',
                'status_code': response.status_code
            }
    
    except requests.exceptions.Timeout:
        return {
            'valid': False,
            'message': 'Coupon validation timed out. Please try again.',
            'status_code': 0
        }
    
    except requests.exceptions.ConnectionError:
        return {
            'valid': False,
            'message': 'Unable to connect to FunderPro API. Please check your internet connection.',
            'status_code': 0
        }
    
    except Exception as e:
        print(f"[COUPON] Validation error: {e}")
        return {
            'valid': False,
            'message': 'An error occurred while validating the coupon. Please try again.',
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
        "alpha",  # Valid test coupon from screenshot
        "INVALID123",  # Should fail
        "",  # Empty string
    ]
    
    for code in test_codes:
        print(f"Testing: '{code}'")
        result = validate_coupon(code)
        print(f"  Valid: {result['valid']}")
        print(f"  Message: {result['message']}")
        print(f"  Status: {result['status_code']}\n")
