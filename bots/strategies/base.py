"""
Base strategy class for signal generation
All strategies inherit from this class
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from bots.core.indicator_utils import indicator_utils
from db import get_forex_config


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    def __init__(self):
        self.name = 'base'
        self.symbol = 'XAU/USD'
        self.timeframe = '15min'
        self.indicators = indicator_utils
        self.load_config()
    
    def load_config(self):
        """Load configuration from database"""
        try:
            config = get_forex_config()
            if config:
                self.trading_start_hour = config.get('trading_start_hour', 8)
                self.trading_end_hour = config.get('trading_end_hour', 22)
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0)
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0)
            else:
                self.trading_start_hour = 8
                self.trading_end_hour = 22
                self.atr_sl_multiplier = 2.0
                self.atr_tp_multiplier = 4.0
        except Exception as e:
            print(f"[{self.name.upper()}] Config load error: {e}")
            self.trading_start_hour = 8
            self.trading_end_hour = 22
            self.atr_sl_multiplier = 2.0
            self.atr_tp_multiplier = 4.0
    
    def reload_config(self):
        """Reload configuration from database"""
        self.load_config()
    
    def is_trading_hours(self) -> bool:
        """Check if current time is within trading hours"""
        from datetime import datetime
        now = datetime.utcnow()
        return self.trading_start_hour <= now.hour < self.trading_end_hour
    
    @abstractmethod
    def check_buy_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if buy conditions are met
        
        Args:
            indicators: Dict with all indicator values
        
        Returns:
            Dict with signal reasons if conditions met, None otherwise
        """
        pass
    
    @abstractmethod
    def check_sell_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if sell conditions are met
        
        Args:
            indicators: Dict with all indicator values
        
        Returns:
            Dict with signal reasons if conditions met, None otherwise
        """
        pass
    
    async def check_for_signal(self) -> Optional[Dict[str, Any]]:
        """
        Check market conditions and generate signal if conditions met
        
        Returns:
            Signal data dict or None if no signal
        """
        try:
            if not self.is_trading_hours():
                print(f"[{self.name.upper()}] Outside trading hours")
                return None
            
            print(f"\n[{self.name.upper()}] Checking for signals on {self.symbol} {self.timeframe}...")
            
            indicators = await self.indicators.get_all_indicators(self.timeframe)
            if not indicators:
                print(f"[{self.name.upper()}] Failed to fetch indicators")
                return None
            
            price = indicators['price']
            rsi = indicators['rsi']
            macd = indicators['macd']
            adx = indicators['adx']
            atr = indicators['atr']
            
            print(f"[{self.name.upper()}] Price: {price:.2f}, RSI: {rsi:.2f}, ADX: {adx:.2f}")
            
            buy_result = self.check_buy_conditions(indicators)
            if buy_result:
                tp, sl = self.indicators.calculate_tp_sl(
                    price, atr, 'BUY', 
                    self.atr_sl_multiplier, self.atr_tp_multiplier
                )
                
                signal_data = {
                    'signal_type': 'BUY',
                    'bot_type': self.name,
                    'pair': self.symbol,
                    'timeframe': self.timeframe,
                    'entry_price': price,
                    'take_profit': tp,
                    'stop_loss': sl,
                    'rsi_value': rsi,
                    'macd_value': macd['macd'],
                    'atr_value': atr,
                    'indicators_used': buy_result.get('indicators', {}),
                    'notes': buy_result.get('reason', '')
                }
                
                print(f"[{self.name.upper()}] BUY signal @ {price:.2f}, TP: {tp:.2f}, SL: {sl:.2f}")
                return signal_data
            
            sell_result = self.check_sell_conditions(indicators)
            if sell_result:
                tp, sl = self.indicators.calculate_tp_sl(
                    price, atr, 'SELL',
                    self.atr_sl_multiplier, self.atr_tp_multiplier
                )
                
                signal_data = {
                    'signal_type': 'SELL',
                    'bot_type': self.name,
                    'pair': self.symbol,
                    'timeframe': self.timeframe,
                    'entry_price': price,
                    'take_profit': tp,
                    'stop_loss': sl,
                    'rsi_value': rsi,
                    'macd_value': macd['macd'],
                    'atr_value': atr,
                    'indicators_used': sell_result.get('indicators', {}),
                    'notes': sell_result.get('reason', '')
                }
                
                print(f"[{self.name.upper()}] SELL signal @ {price:.2f}, TP: {tp:.2f}, SL: {sl:.2f}")
                return signal_data
            
            print(f"[{self.name.upper()}] No signal conditions met")
            return None
            
        except Exception as e:
            print(f"[{self.name.upper()}] Error checking for signal: {e}")
            return None
