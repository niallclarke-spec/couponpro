"""
Centralized Pip Calculator for XAU/USD (Gold) Trading

This module provides the single source of truth for all pip calculations
across the platform. All forex-related code should import from here.

For XAU/USD:
- 1 pip = $0.10 price movement
- $1.00 price movement = 10 pips
- Example: Entry $2750.00 to Exit $2755.00 = 50 pips

This constant can be made tenant-specific in the future if different
brokers use different pip definitions.
"""
from typing import Union


PIP_VALUE = 0.10
PIPS_MULTIPLIER = 10
USD_PER_PIP_PER_LOT = 1.0
COMMISSION_PER_LOT = 7.0


def calculate_pips(
    entry_price: float, 
    exit_price: float, 
    direction: str
) -> float:
    """
    Calculate pips for XAU/USD trade.
    
    Formula: price_change / PIP_VALUE = price_change * PIPS_MULTIPLIER
    For XAU/USD: $0.10 = 1 pip
    
    Args:
        entry_price: Entry price
        exit_price: Exit/TP/SL price  
        direction: "BUY" or "SELL"
        
    Returns:
        Pips (positive for profit, negative for loss)
    """
    if direction.upper() == "BUY":
        return round((exit_price - entry_price) * PIPS_MULTIPLIER, 1)
    else:
        return round((entry_price - exit_price) * PIPS_MULTIPLIER, 1)


def price_to_pips(price_difference: float) -> float:
    """
    Convert a price difference to pips.
    
    Args:
        price_difference: Raw price difference (can be negative)
        
    Returns:
        Pips value (preserves sign)
    """
    return round(price_difference * PIPS_MULTIPLIER, 1)


def pips_to_price(pips: float) -> float:
    """
    Convert pips to price difference.
    
    Args:
        pips: Number of pips
        
    Returns:
        Price difference in dollars
    """
    return round(pips * PIP_VALUE, 2)


def calculate_profit_from_pips(
    pips: float, 
    lot_size: float = 1.0, 
    include_commission: bool = True
) -> float:
    """
    Calculate net profit from pips.
    
    For XAU/USD with standard lot (100 oz):
    - 1 pip ($0.10) × 100 oz = $10 per pip per lot
    - But our USD_PER_PIP_PER_LOT is configured as $1.0
    
    Args:
        pips: Number of pips
        lot_size: Lot size (default 1.0)
        include_commission: Whether to deduct commission
        
    Returns:
        Net profit in USD
    """
    gross_profit = pips * USD_PER_PIP_PER_LOT * lot_size
    commission = COMMISSION_PER_LOT * lot_size if include_commission else 0
    return round(gross_profit - commission, 2)
