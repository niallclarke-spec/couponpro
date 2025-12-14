#!/usr/bin/env python3
"""
Stripe Rebill Calculator Test
Smoke test: python3 scripts/test_stripe_rebill.py

Tests _get_next_rebill_from_subscription with mocked data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
import time

def test_rebill_with_missing_period_end():
    """Test that rebill calculator falls back to Invoice.create_preview when current_period_end is missing."""
    
    # Import after path setup
    from integrations.stripe import client as stripe_client_module
    
    # Mock subscription without current_period_end
    mock_sub = MagicMock()
    mock_sub.id = 'sub_test123456789'
    mock_sub.get = MagicMock(return_value=None)  # No current_period_end
    mock_sub.current_period_end = None
    mock_sub.items = None
    
    # Mock Invoice.create_preview response
    mock_preview = MagicMock()
    mock_preview.period_end = 1735689600  # Jan 1, 2025
    mock_preview.amount_due = 9900  # $99.00 in cents
    mock_preview.total = 9900
    
    mock_stripe = MagicMock()
    mock_stripe.Invoice.create_preview.return_value = mock_preview
    
    # Clear cache
    stripe_client_module._upcoming_invoice_cache = {}
    
    # Call the helper
    result = stripe_client_module._get_next_rebill_from_subscription(mock_stripe, mock_sub)
    
    # Verify result
    assert result is not None, "Expected (timestamp, amount), got None"
    ts, amount = result
    assert ts == 1735689600, f"Expected timestamp 1735689600, got {ts}"
    assert amount == 9900, f"Expected amount 9900 cents, got {amount}"
    
    # Verify Invoice.create_preview was called
    mock_stripe.Invoice.create_preview.assert_called_once_with(subscription='sub_test123456789')
    
    print("✅ test_rebill_with_missing_period_end PASSED")

def test_rebill_with_period_end():
    """Test that rebill calculator uses subscription data when current_period_end exists."""
    
    from integrations.stripe import client as stripe_client_module
    
    # Mock subscription WITH current_period_end
    mock_price = MagicMock()
    mock_price.unit_amount = 4900  # $49.00
    
    mock_item = MagicMock()
    mock_item.price = mock_price
    mock_item.quantity = 1
    
    mock_items = MagicMock()
    mock_items.data = [mock_item]
    
    mock_sub = MagicMock()
    mock_sub.id = 'sub_with_period'
    mock_sub.current_period_end = 1735689600
    mock_sub.get = MagicMock(return_value=1735689600)
    mock_sub.items = mock_items
    
    mock_stripe = MagicMock()
    
    # Clear cache
    stripe_client_module._upcoming_invoice_cache = {}
    
    result = stripe_client_module._get_next_rebill_from_subscription(mock_stripe, mock_sub)
    
    assert result is not None, "Expected (timestamp, amount), got None"
    ts, amount = result
    assert ts == 1735689600, f"Expected timestamp 1735689600, got {ts}"
    assert amount == 4900, f"Expected amount 4900 cents, got {amount}"
    
    # Verify Invoice.create_preview was NOT called (we got data from subscription)
    mock_stripe.Invoice.create_preview.assert_not_called()
    
    print("✅ test_rebill_with_period_end PASSED")

def test_cache_works():
    """Test that cache prevents duplicate API calls."""
    
    from integrations.stripe import client as stripe_client_module
    
    mock_sub = MagicMock()
    mock_sub.id = 'sub_cache_test'
    mock_sub.get = MagicMock(return_value=None)
    mock_sub.current_period_end = None
    mock_sub.items = None
    
    mock_preview = MagicMock()
    mock_preview.period_end = 1735689600
    mock_preview.amount_due = 5000
    
    mock_stripe = MagicMock()
    mock_stripe.Invoice.create_preview.return_value = mock_preview
    
    # Clear cache
    stripe_client_module._upcoming_invoice_cache = {}
    
    # First call - should hit API
    result1 = stripe_client_module._get_next_rebill_from_subscription(mock_stripe, mock_sub)
    
    # Second call - should use cache
    result2 = stripe_client_module._get_next_rebill_from_subscription(mock_stripe, mock_sub)
    
    assert result1 == result2, "Cache should return same result"
    assert mock_stripe.Invoice.create_preview.call_count == 1, "API should only be called once due to cache"
    
    print("✅ test_cache_works PASSED")

if __name__ == '__main__':
    print("Running Stripe rebill calculator tests...")
    print()
    test_rebill_with_missing_period_end()
    test_rebill_with_period_end()
    test_cache_works()
    print()
    print("All tests passed! ✅")
