"""
Twelve Data API client for forex signals
Fetches RSI, MACD, ATR, and real-time price data for XAU/USD

NOTE: This is now a shim that re-exports from integrations.market_data.twelve_data
All imports from forex_api continue to work unchanged.
"""
from integrations.market_data.twelve_data import (
    TwelveDataClient,
    twelve_data_client,
    get_twelve_data_client,
    get_current_price
)

__all__ = [
    'TwelveDataClient',
    'twelve_data_client',
    'get_twelve_data_client', 
    'get_current_price'
]
