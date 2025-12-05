"""
Indicator utilities for signal generation
Wraps Twelve Data API calls with rate limiting
Uses asyncio for non-blocking operations
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from forex_api import twelve_data_client


class IndicatorUtils:
    """Utility class for fetching and processing technical indicators"""
    
    def __init__(self, symbol='XAU/USD'):
        self.symbol = symbol
        self.api = twelve_data_client
        self.rate_limit_delay = 8
        self._executor = ThreadPoolExecutor(max_workers=2)
    
    async def fetch_with_rate_limit(self, func, *args, delay=None):
        """Fetch indicator with rate limiting to avoid API limits (non-blocking)"""
        if delay is None:
            delay = self.rate_limit_delay
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, func, *args)
        
        if delay > 0:
            await asyncio.sleep(delay)
        return result
    
    def get_current_price(self):
        """Get current price"""
        return self.api.get_price(self.symbol)
    
    def get_rsi(self, timeframe='15min', period=14):
        """Get RSI value"""
        return self.fetch_with_rate_limit(self.api.get_rsi, self.symbol, timeframe)
    
    def get_macd(self, timeframe='15min'):
        """Get MACD data (macd, signal, histogram, histogram_slope)"""
        return self.fetch_with_rate_limit(self.api.get_macd, self.symbol, timeframe)
    
    def get_atr(self, timeframe='15min', period=14):
        """Get ATR value for volatility-based TP/SL"""
        return self.fetch_with_rate_limit(self.api.get_atr, self.symbol, timeframe)
    
    def get_adx(self, timeframe='15min', period=14):
        """Get ADX value for trend strength"""
        return self.fetch_with_rate_limit(self.api.get_adx, self.symbol, timeframe)
    
    def get_bbands(self, timeframe='15min', period=20):
        """Get Bollinger Bands (upper, middle, lower)"""
        return self.fetch_with_rate_limit(self.api.get_bbands, self.symbol, timeframe)
    
    def get_stoch(self, timeframe='15min'):
        """Get Stochastic oscillator (k, d, is_oversold, is_overbought)"""
        return self.fetch_with_rate_limit(self.api.get_stoch, self.symbol, timeframe)
    
    def get_ema(self, timeframe='1h', period=50):
        """Get EMA value"""
        return self.fetch_with_rate_limit(self.api.get_ema, self.symbol, timeframe, period)
    
    async def get_all_indicators(self, timeframe='15min'):
        """
        Fetch all indicators needed for signal analysis
        Returns dict with all indicator values or None if any failed
        """
        try:
            price = await self.fetch_with_rate_limit(self.api.get_price, self.symbol)
            rsi = await self.fetch_with_rate_limit(self.api.get_rsi, self.symbol, timeframe)
            macd = await self.fetch_with_rate_limit(self.api.get_macd, self.symbol, timeframe)
            atr = await self.fetch_with_rate_limit(self.api.get_atr, self.symbol, timeframe)
            adx = await self.fetch_with_rate_limit(self.api.get_adx, self.symbol, timeframe)
            bbands = await self.fetch_with_rate_limit(self.api.get_bbands, self.symbol, timeframe)
            stoch = await self.fetch_with_rate_limit(self.api.get_stoch, self.symbol, timeframe)
            ema50 = await self.fetch_with_rate_limit(self.api.get_ema, self.symbol, '1h', 50)
            ema200 = await self.fetch_with_rate_limit(self.api.get_ema, self.symbol, '1h', 200, delay=0)
            
            if not all([price, rsi, macd, atr, adx, bbands, stoch, ema50, ema200]):
                return None
            
            return {
                'price': price,
                'rsi': rsi,
                'macd': macd,
                'atr': atr,
                'adx': adx,
                'bbands': bbands,
                'stoch': stoch,
                'ema50': ema50,
                'ema200': ema200,
                'trend_bullish': ema50 > ema200,
                'trend_bearish': ema50 < ema200
            }
        except Exception as e:
            print(f"[INDICATORS] Error fetching indicators: {e}")
            return None
    
    def calculate_tp_sl(self, entry_price, atr_value, signal_type, sl_multiplier=2.0, tp_multiplier=4.0):
        """
        Calculate Take Profit and Stop Loss using ATR-based method
        
        Args:
            entry_price: Entry price for the signal
            atr_value: Current ATR value
            signal_type: 'BUY' or 'SELL'
            sl_multiplier: ATR multiplier for stop loss
            tp_multiplier: ATR multiplier for take profit
        
        Returns:
            tuple: (take_profit, stop_loss)
        """
        if signal_type == 'BUY':
            stop_loss = round(entry_price - (atr_value * sl_multiplier), 2)
            take_profit = round(entry_price + (atr_value * tp_multiplier), 2)
        else:
            stop_loss = round(entry_price + (atr_value * sl_multiplier), 2)
            take_profit = round(entry_price - (atr_value * tp_multiplier), 2)
        
        return take_profit, stop_loss


indicator_utils = IndicatorUtils()
