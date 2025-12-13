"""
Twelve Data API client for forex signals
Fetches RSI, MACD, ATR, and real-time price data for XAU/USD

NOTE: This is now a shim that re-exports from integrations.market_data.twelve_data
All imports from forex_api continue to work unchanged.
"""
from integrations.market_data.twelve_data import (
    TwelveDataClient,
    get_twelve_data_client,
    get_current_price
)

class _LazyClient:
    """Lazy wrapper that provides twelve_data_client access without import-time instantiation"""
    def __getattr__(self, name):
        return getattr(get_twelve_data_client(), name)

twelve_data_client = _LazyClient()

__all__ = [
    'TwelveDataClient',
    'twelve_data_client',
    'get_twelve_data_client', 
    'get_current_price'
]
