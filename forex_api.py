"""
Twelve Data API client for forex signals
Fetches RSI, MACD, ATR, and real-time price data for XAU/USD
"""
import os
import requests
from datetime import datetime

class TwelveDataClient:
    def __init__(self):
        self.api_key = os.environ.get('TWELVE_DATA_API_KEY')
        self.base_url = 'https://api.twelvedata.com'
        
        if not self.api_key:
            print("⚠️  TWELVE_DATA_API_KEY not set - forex signals will not work")
    
    def _make_request(self, endpoint, params):
        """Make API request to Twelve Data"""
        if not self.api_key:
            raise Exception("TWELVE_DATA_API_KEY not configured")
        
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'error':
                raise Exception(f"Twelve Data API error: {data.get('message', 'Unknown error')}")
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"❌ Twelve Data API request failed: {e}")
            raise
    
    def get_price(self, symbol='XAU/USD'):
        """Get current price for a forex pair"""
        try:
            data = self._make_request('price', {'symbol': symbol})
            return float(data.get('price', 0))
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_rsi(self, symbol='XAU/USD', interval='15min', period=14):
        """
        Get RSI (Relative Strength Index) value
        
        Args:
            symbol: Trading pair (default: XAU/USD)
            interval: Time interval (15min, 30min, 1h, etc.)
            period: RSI period (default: 14)
        
        Returns:
            float: RSI value (0-100) or None if error
        """
        try:
            data = self._make_request('rsi', {
                'symbol': symbol,
                'interval': interval,
                'time_period': period,
                'outputsize': 1
            })
            
            if 'values' in data and len(data['values']) > 0:
                return float(data['values'][0]['rsi'])
            return None
        except Exception as e:
            print(f"Error fetching RSI for {symbol}: {e}")
            return None
    
    def get_macd(self, symbol='XAU/USD', interval='15min'):
        """
        Get MACD (Moving Average Convergence Divergence) values
        
        Args:
            symbol: Trading pair (default: XAU/USD)
            interval: Time interval (15min, 30min, 1h, etc.)
        
        Returns:
            dict: {
                'macd': MACD line value,
                'signal': Signal line value,
                'histogram': MACD histogram value,
                'is_bullish_cross': True if MACD just crossed above signal,
                'is_bearish_cross': True if MACD just crossed below signal
            } or None if error
        """
        try:
            data = self._make_request('macd', {
                'symbol': symbol,
                'interval': interval,
                'series_type': 'close',
                'outputsize': 2
            })
            
            if 'values' in data and len(data['values']) >= 2:
                current = data['values'][0]
                previous = data['values'][1]
                
                macd_current = float(current['macd'])
                signal_current = float(current['macd_signal'])
                macd_previous = float(previous['macd'])
                signal_previous = float(previous['macd_signal'])
                
                bullish_cross = macd_previous <= signal_previous and macd_current > signal_current
                bearish_cross = macd_previous >= signal_previous and macd_current < signal_current
                
                return {
                    'macd': macd_current,
                    'signal': signal_current,
                    'histogram': float(current['macd_hist']),
                    'is_bullish_cross': bullish_cross,
                    'is_bearish_cross': bearish_cross
                }
            return None
        except Exception as e:
            print(f"Error fetching MACD for {symbol}: {e}")
            return None
    
    def get_atr(self, symbol='XAU/USD', interval='15min', period=14):
        """
        Get ATR (Average True Range) value for dynamic stop loss/take profit
        
        Args:
            symbol: Trading pair (default: XAU/USD)
            interval: Time interval (15min, 30min, 1h, etc.)
            period: ATR period (default: 14)
        
        Returns:
            float: ATR value or None if error
        """
        try:
            data = self._make_request('atr', {
                'symbol': symbol,
                'interval': interval,
                'time_period': period,
                'outputsize': 1
            })
            
            if 'values' in data and len(data['values']) > 0:
                return float(data['values'][0]['atr'])
            return None
        except Exception as e:
            print(f"Error fetching ATR for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol='XAU/USD'):
        """
        Get full quote with OHLC, volume, and price change
        
        Returns:
            dict: Quote data with open, high, low, close, volume, etc.
        """
        try:
            data = self._make_request('quote', {'symbol': symbol})
            return data
        except Exception as e:
            print(f"Error fetching quote for {symbol}: {e}")
            return None

twelve_data_client = TwelveDataClient()
