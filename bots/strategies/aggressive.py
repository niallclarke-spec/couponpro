"""
Aggressive trading strategy
Generates more signals with looser conditions
Lower confirmation requirements, wider entry zones
"""
from typing import Optional, Dict, Any
from bots.strategies.base import BaseStrategy
from db import get_forex_config
from core.logging import get_logger

logger = get_logger(__name__)


class AggressiveStrategy(BaseStrategy):
    """
    Aggressive strategy - more signals, looser conditions
    
    Entry conditions:
    - RSI extremes (35/65) with 1 confirmation
    - ADX threshold: 10 (weak trend OK)
    - Wider ATR multipliers for TP/SL
    """
    
    def __init__(self, tenant_id=None):
        super().__init__(tenant_id=tenant_id)
        self.name = 'aggressive'
        self.load_strategy_config()
    
    def load_strategy_config(self):
        """Load aggressive-specific configuration"""
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40) + 5
                self.rsi_overbought = config.get('rsi_overbought', 60) - 5
                self.adx_threshold = max(5, config.get('adx_threshold', 15) - 10)
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0) * 1.2
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0) * 1.2
            else:
                self.rsi_oversold = 45
                self.rsi_overbought = 55
                self.adx_threshold = 5
                self.atr_sl_multiplier = 2.4
                self.atr_tp_multiplier = 4.8
        except Exception as e:
            logger.error(f"Config error: {e}")
            self.rsi_oversold = 45
            self.rsi_overbought = 55
            self.adx_threshold = 5
            self.atr_sl_multiplier = 2.4
            self.atr_tp_multiplier = 4.8
    
    def check_buy_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Aggressive BUY conditions:
        - RSI < 45 (looser than conservative)
        - ADX > 5 (weak trend acceptable)
        - At least 1 confirmation: BB touch OR Stochastic oversold
        """
        rsi = indicators['rsi']
        adx = indicators['adx']
        price = indicators['price']
        atr = indicators['atr']
        bbands = indicators['bbands']
        stoch = indicators['stoch']
        
        if adx < self.adx_threshold:
            logger.info(f"ADX {adx:.2f} < {self.adx_threshold}, too weak")
            return None
        
        if rsi >= self.rsi_oversold:
            return None
        
        confirmations = []
        indicators_used = {'rsi': rsi, 'adx': adx}
        
        bb_distance = abs(price - bbands['lower'])
        bb_touch = bb_distance < (atr * 0.7)
        if bb_touch:
            confirmations.append("BB_lower_touch")
            indicators_used['bb_lower'] = bbands['lower']
        
        if stoch['is_oversold']:
            confirmations.append("Stoch_oversold")
            indicators_used['stoch_k'] = stoch['k']
        
        if len(confirmations) >= 1:
            return {
                'reason': f"Aggressive BUY: RSI={rsi:.1f}, {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None
    
    def check_sell_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Aggressive SELL conditions:
        - RSI > 55 (looser than conservative)
        - ADX > 5 (weak trend acceptable)
        - At least 1 confirmation: BB touch OR Stochastic overbought
        """
        rsi = indicators['rsi']
        adx = indicators['adx']
        price = indicators['price']
        atr = indicators['atr']
        bbands = indicators['bbands']
        stoch = indicators['stoch']
        
        if adx < self.adx_threshold:
            return None
        
        if rsi <= self.rsi_overbought:
            return None
        
        confirmations = []
        indicators_used = {'rsi': rsi, 'adx': adx}
        
        bb_distance = abs(price - bbands['upper'])
        bb_touch = bb_distance < (atr * 0.7)
        if bb_touch:
            confirmations.append("BB_upper_touch")
            indicators_used['bb_upper'] = bbands['upper']
        
        if stoch['is_overbought']:
            confirmations.append("Stoch_overbought")
            indicators_used['stoch_k'] = stoch['k']
        
        if len(confirmations) >= 1:
            return {
                'reason': f"Aggressive SELL: RSI={rsi:.1f}, {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None


aggressive_strategy = AggressiveStrategy()
