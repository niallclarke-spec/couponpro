"""
Custom trading strategy
User-configurable indicator combinations and thresholds
Allows building custom rules from multiple indicators
"""
from typing import Optional, Dict, Any, List
from bots.strategies.base import BaseStrategy
from db import get_forex_config, db_pool
from core.logging import get_logger

logger = get_logger(__name__)


class CustomStrategy(BaseStrategy):
    """
    Custom strategy - user-defined indicator rules
    
    Configurable:
    - Which indicators to use (RSI, MACD, ADX, BB, Stoch, EMA)
    - Threshold values for each indicator
    - Number of confirmations required
    - TP/SL multipliers
    """
    
    def __init__(self, tenant_id: str = None):
        super().__init__(tenant_id=tenant_id)
        self.name = 'custom'
        self.active_indicators = []
        self.required_confirmations = 2
        self.custom_config = {}
        self.load_strategy_config()
    
    def load_strategy_config(self):
        """Load custom strategy configuration from database"""
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40)
                self.rsi_overbought = config.get('rsi_overbought', 60)
                self.adx_threshold = config.get('adx_threshold', 15)
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0)
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0)
            else:
                self.rsi_oversold = 40
                self.rsi_overbought = 60
                self.adx_threshold = 15
                self.atr_sl_multiplier = 2.0
                self.atr_tp_multiplier = 4.0
            
            self.custom_config = self._load_custom_config()
            
            self.active_indicators = self.custom_config.get('indicators', ['rsi', 'macd', 'bb', 'stoch'])
            self.required_confirmations = self.custom_config.get('required_confirmations', 2)
            self.require_trend_alignment = self.custom_config.get('require_trend', False)
            
            if 'rsi_oversold' in self.custom_config:
                self.rsi_oversold = self.custom_config['rsi_oversold']
            if 'rsi_overbought' in self.custom_config:
                self.rsi_overbought = self.custom_config['rsi_overbought']
            if 'adx_threshold' in self.custom_config:
                self.adx_threshold = self.custom_config['adx_threshold']
                
        except Exception as e:
            logger.error(f"Config error: {e}")
            self.active_indicators = ['rsi', 'macd', 'bb', 'stoch']
            self.required_confirmations = 2
            self.require_trend_alignment = False
    
    def _load_custom_config(self) -> Dict[str, Any]:
        """Load custom strategy config from bot_config table"""
        try:
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT setting_value FROM bot_config 
                    WHERE setting_key = 'custom_strategy_config'
                """)
                row = cursor.fetchone()
                if row and row[0]:
                    import json
                    return json.loads(row[0])
                return {}
        except Exception as e:
            logger.error(f"Error loading custom config: {e}")
            return {}
    
    def save_custom_config(self, config: Dict[str, Any]) -> bool:
        """Save custom strategy configuration to database"""
        try:
            import json
            config_json = json.dumps(config)
            
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO bot_config (setting_key, setting_value, updated_at)
                    VALUES ('custom_strategy_config', %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (setting_key) 
                    DO UPDATE SET setting_value = %s, updated_at = CURRENT_TIMESTAMP
                """, (config_json, config_json))
                conn.commit()
                
            self.custom_config = config
            self.load_strategy_config()
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def _check_rsi(self, rsi: float, direction: str) -> Optional[str]:
        """Check RSI condition"""
        if 'rsi' not in self.active_indicators:
            return None
        
        if direction == 'BUY' and rsi < self.rsi_oversold:
            return f"RSI_oversold({rsi:.1f})"
        elif direction == 'SELL' and rsi > self.rsi_overbought:
            return f"RSI_overbought({rsi:.1f})"
        return None
    
    def _check_macd(self, macd: Dict, direction: str) -> Optional[str]:
        """Check MACD condition"""
        if 'macd' not in self.active_indicators:
            return None
        
        if direction == 'BUY' and macd['histogram_slope'] > 0:
            return "MACD_bullish"
        elif direction == 'SELL' and macd['histogram_slope'] < 0:
            return "MACD_bearish"
        return None
    
    def _check_bb(self, price: float, bbands: Dict, atr: float, direction: str) -> Optional[str]:
        """Check Bollinger Bands condition"""
        if 'bb' not in self.active_indicators:
            return None
        
        if direction == 'BUY':
            distance = abs(price - bbands['lower'])
            if distance < (atr * 0.5):
                return "BB_lower_touch"
        elif direction == 'SELL':
            distance = abs(price - bbands['upper'])
            if distance < (atr * 0.5):
                return "BB_upper_touch"
        return None
    
    def _check_stoch(self, stoch: Dict, direction: str) -> Optional[str]:
        """Check Stochastic condition"""
        if 'stoch' not in self.active_indicators:
            return None
        
        if direction == 'BUY' and stoch['is_oversold']:
            return f"Stoch_oversold({stoch['k']:.1f})"
        elif direction == 'SELL' and stoch['is_overbought']:
            return f"Stoch_overbought({stoch['k']:.1f})"
        return None
    
    def _check_adx(self, adx: float) -> bool:
        """Check if ADX meets threshold"""
        if 'adx' not in self.active_indicators:
            return True
        return adx >= self.adx_threshold
    
    def _check_trend(self, indicators: Dict, direction: str) -> bool:
        """Check trend alignment if required"""
        if not self.require_trend_alignment:
            return True
        
        if direction == 'BUY':
            return indicators['trend_bullish']
        else:
            return indicators['trend_bearish']
    
    def check_buy_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check custom BUY conditions based on active indicators"""
        if not self._check_adx(indicators['adx']):
            logger.info(f"ADX {indicators['adx']:.2f} < {self.adx_threshold}")
            return None
        
        if not self._check_trend(indicators, 'BUY'):
            return None
        
        confirmations = []
        indicators_used = {'adx': indicators['adx']}
        
        rsi_check = self._check_rsi(indicators['rsi'], 'BUY')
        if rsi_check:
            confirmations.append(rsi_check)
            indicators_used['rsi'] = indicators['rsi']
        
        macd_check = self._check_macd(indicators['macd'], 'BUY')
        if macd_check:
            confirmations.append(macd_check)
            indicators_used['macd'] = indicators['macd']['macd']
        
        bb_check = self._check_bb(indicators['price'], indicators['bbands'], indicators['atr'], 'BUY')
        if bb_check:
            confirmations.append(bb_check)
            indicators_used['bb_lower'] = indicators['bbands']['lower']
        
        stoch_check = self._check_stoch(indicators['stoch'], 'BUY')
        if stoch_check:
            confirmations.append(stoch_check)
            indicators_used['stoch_k'] = indicators['stoch']['k']
        
        if len(confirmations) >= self.required_confirmations:
            return {
                'reason': f"Custom BUY: {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None
    
    def check_sell_conditions(self, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check custom SELL conditions based on active indicators"""
        if not self._check_adx(indicators['adx']):
            return None
        
        if not self._check_trend(indicators, 'SELL'):
            return None
        
        confirmations = []
        indicators_used = {'adx': indicators['adx']}
        
        rsi_check = self._check_rsi(indicators['rsi'], 'SELL')
        if rsi_check:
            confirmations.append(rsi_check)
            indicators_used['rsi'] = indicators['rsi']
        
        macd_check = self._check_macd(indicators['macd'], 'SELL')
        if macd_check:
            confirmations.append(macd_check)
            indicators_used['macd'] = indicators['macd']['macd']
        
        bb_check = self._check_bb(indicators['price'], indicators['bbands'], indicators['atr'], 'SELL')
        if bb_check:
            confirmations.append(bb_check)
            indicators_used['bb_upper'] = indicators['bbands']['upper']
        
        stoch_check = self._check_stoch(indicators['stoch'], 'SELL')
        if stoch_check:
            confirmations.append(stoch_check)
            indicators_used['stoch_k'] = indicators['stoch']['k']
        
        if len(confirmations) >= self.required_confirmations:
            return {
                'reason': f"Custom SELL: {', '.join(confirmations)}",
                'indicators': indicators_used
            }
        
        return None


custom_strategy = CustomStrategy()
