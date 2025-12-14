"""
Conservative trading strategy
Fewer signals with stricter conditions
Requires multiple confirmations, trend alignment, stronger ADX
"""
from typing import Optional, Dict, Any
from bots.strategies.base import BaseStrategy
from db import get_forex_config


class ConservativeStrategy(BaseStrategy):
    """
    Conservative strategy - fewer signals, stricter conditions
    
    Entry conditions:
    - RSI extremes (30/70) - must be at real extremes
    - ADX threshold: 25 (strong trend required)
    - Trend alignment: Must match EMA direction
    - Requires 2+ confirmations
    - Tighter ATR multipliers for TP/SL
    """
    
    def __init__(self, tenant_id=None):
        super().__init__(tenant_id=tenant_id)
        self.name = 'conservative'
        self.load_strategy_config()
    
    def load_strategy_config(self):
        """Load conservative-specific configuration"""
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40) - 10
                self.rsi_overbought = config.get('rsi_overbought', 60) + 10
                self.adx_threshold = config.get('adx_threshold', 15) + 10
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0) * 0.8
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0) * 0.8
            else:
                self.rsi_oversold = 30
                self.rsi_overbought = 70
                self.adx_threshold = 25
                self.atr_sl_multiplier = 1.6
                self.atr_tp_multiplier = 3.2
        except Exception as e:
            print(f"[CONSERVATIVE] Config error: {e}")
            self.rsi_oversold = 30
            self.rsi_overbought = 70
            self.adx_threshold = 25
            self.atr_sl_multiplier = 1.6
            self.atr_tp_multiplier = 3.2
    
    def check_buy_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Conservative BUY conditions:
        - Trend must be bullish (EMA50 > EMA200)
        - RSI < 30 (extreme oversold)
        - ADX > 25 (strong trend)
        - At least 2 confirmations: BB touch, Stochastic, MACD
        """
        rsi = indicators['rsi']
        adx = indicators['adx']
        price = indicators['price']
        atr = indicators['atr']
        bbands = indicators['bbands']
        stoch = indicators['stoch']
        macd = indicators['macd']
        trend_bullish = indicators['trend_bullish']
        
        if not trend_bullish:
            return None
        
        if adx < self.adx_threshold:
            print(f"[CONSERVATIVE] ADX {adx:.2f} < {self.adx_threshold}, trend too weak")
            return None
        
        if rsi >= self.rsi_oversold:
            return None
        
        confirmations = []
        indicators_used = {'rsi': rsi, 'adx': adx, 'ema50': indicators['ema50'], 'ema200': indicators['ema200']}
        
        bb_distance = abs(price - bbands['lower'])
        bb_touch = bb_distance < (atr * 0.4)
        if bb_touch:
            confirmations.append("BB_lower_touch")
            indicators_used['bb_lower'] = bbands['lower']
        
        if stoch['is_oversold']:
            confirmations.append("Stoch_oversold")
            indicators_used['stoch_k'] = stoch['k']
        
        if macd['histogram_slope'] > 0:
            confirmations.append("MACD_bullish_divergence")
            indicators_used['macd_histogram'] = macd['histogram']
        
        if len(confirmations) >= 2:
            return {
                'reason': f"Conservative BUY: Bullish trend, RSI={rsi:.1f}, {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None
    
    def check_sell_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Conservative SELL conditions:
        - Trend must be bearish (EMA50 < EMA200)
        - RSI > 70 (extreme overbought)
        - ADX > 25 (strong trend)
        - At least 2 confirmations: BB touch, Stochastic, MACD
        """
        rsi = indicators['rsi']
        adx = indicators['adx']
        price = indicators['price']
        atr = indicators['atr']
        bbands = indicators['bbands']
        stoch = indicators['stoch']
        macd = indicators['macd']
        trend_bearish = indicators['trend_bearish']
        
        if not trend_bearish:
            return None
        
        if adx < self.adx_threshold:
            return None
        
        if rsi <= self.rsi_overbought:
            return None
        
        confirmations = []
        indicators_used = {'rsi': rsi, 'adx': adx, 'ema50': indicators['ema50'], 'ema200': indicators['ema200']}
        
        bb_distance = abs(price - bbands['upper'])
        bb_touch = bb_distance < (atr * 0.4)
        if bb_touch:
            confirmations.append("BB_upper_touch")
            indicators_used['bb_upper'] = bbands['upper']
        
        if stoch['is_overbought']:
            confirmations.append("Stoch_overbought")
            indicators_used['stoch_k'] = stoch['k']
        
        if macd['histogram_slope'] < 0:
            confirmations.append("MACD_bearish_divergence")
            indicators_used['macd_histogram'] = macd['histogram']
        
        if len(confirmations) >= 2:
            return {
                'reason': f"Conservative SELL: Bearish trend, RSI={rsi:.1f}, {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None


conservative_strategy = ConservativeStrategy()
