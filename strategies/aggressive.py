"""
Aggressive Strategy
High-risk, high-reward with momentum indicators and lower confirmation thresholds
"""
from typing import Dict, List, Optional, Tuple
from strategies.base_strategy import BaseStrategy, SignalData, TakeProfitLevel
from forex_api import twelve_data_client
from db import get_forex_config, get_daily_pnl, get_last_completed_signal
from datetime import datetime
from core.logging import get_logger

logger = get_logger(__name__)


class AggressiveStrategy(BaseStrategy):
    name = "Aggressive"
    description = "High-risk, high-reward. Uses momentum indicators with lower confirmation thresholds for more frequent signals."
    bot_type = "aggressive"
    
    tp_levels = 3
    tp_percentages = [50, 30, 20]
    
    breakeven_threshold = 70.0
    
    def __init__(self, tenant_id: Optional[str] = None):
        super().__init__(tenant_id=tenant_id)
        self.load_config()
    
    def load_config(self):
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40)
                self.rsi_overbought = config.get('rsi_overbought', 60)
                self.atr_sl_multiplier = float(config.get('atr_sl_multiplier', 1.0))
                self.atr_tp1_multiplier = float(config.get('atr_tp1_multiplier', 1.2))
                self.atr_tp2_multiplier = float(config.get('atr_tp2_multiplier', 2.0))
                self.atr_tp3_multiplier = float(config.get('atr_tp3_multiplier', 2.5))
                self.adx_threshold = config.get('adx_threshold', 15)
                self.trading_start_hour = config.get('trading_start_hour', 8)
                self.trading_end_hour = config.get('trading_end_hour', 22)
                self.daily_loss_cap_pips = float(config.get('daily_loss_cap_pips', 50.0))
                self.back_to_back_throttle_minutes = int(config.get('back_to_back_throttle_minutes', 30))
                session_filter = config.get('session_filter_enabled', 'true')
                self.session_filter_enabled = str(session_filter).lower() == 'true' if isinstance(session_filter, str) else bool(session_filter)
                self.session_start_hour_utc = int(config.get('session_start_hour_utc', 8))
                self.session_end_hour_utc = int(config.get('session_end_hour_utc', 21))
            else:
                self._set_defaults()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._set_defaults()
    
    def _set_defaults(self):
        self.rsi_oversold = 40
        self.rsi_overbought = 60
        self.atr_sl_multiplier = 1.0
        self.atr_tp1_multiplier = 1.2
        self.atr_tp2_multiplier = 2.0
        self.atr_tp3_multiplier = 2.5
        self.adx_threshold = 15
        self.trading_start_hour = 8
        self.trading_end_hour = 22
        self.daily_loss_cap_pips = 50.0
        self.back_to_back_throttle_minutes = 30
        self.session_filter_enabled = True
        self.session_start_hour_utc = 8
        self.session_end_hour_utc = 21
    
    def check_guardrails(self) -> Tuple[bool, Optional[str]]:
        now = datetime.utcnow()
        
        if self.session_filter_enabled:
            current_hour = now.hour
            if not (self.session_start_hour_utc <= current_hour < self.session_end_hour_utc):
                return False, f"Outside trading session ({self.session_start_hour_utc}:00-{self.session_end_hour_utc}:00 UTC)"
        
        daily_pnl = get_daily_pnl(tenant_id=self.tenant_id)
        if daily_pnl <= -self.daily_loss_cap_pips:
            return False, f"Daily loss cap reached ({daily_pnl:.1f} pips, cap: -{self.daily_loss_cap_pips})"
        
        last_signal = get_last_completed_signal(tenant_id=self.tenant_id)
        if last_signal and last_signal['status'] == 'lost':
            closed_at = last_signal['closed_at']
            if closed_at:
                if isinstance(closed_at, str):
                    closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00').replace('+00:00', ''))
                minutes_since_loss = (now - closed_at).total_seconds() / 60
                if minutes_since_loss < self.back_to_back_throttle_minutes:
                    remaining = int(self.back_to_back_throttle_minutes - minutes_since_loss)
                    return False, f"Loss throttle active ({remaining}min remaining after previous loss)"
        
        return True, None
    
    def calculate_tp_sl(self, entry_price: float, atr_value: float, signal_type: str) -> Tuple[List[TakeProfitLevel], float]:
        tp1_pct, tp2_pct, tp3_pct, tp_count = self._get_tp_config()
        
        if signal_type == 'BUY':
            stop_loss = round(entry_price - (atr_value * self.atr_sl_multiplier), 2)
            tp1 = round(entry_price + (atr_value * self.atr_tp1_multiplier), 2)
            tp2 = round(entry_price + (atr_value * self.atr_tp2_multiplier), 2)
            tp3 = round(entry_price + (atr_value * self.atr_tp3_multiplier), 2)
        else:
            stop_loss = round(entry_price + (atr_value * self.atr_sl_multiplier), 2)
            tp1 = round(entry_price - (atr_value * self.atr_tp1_multiplier), 2)
            tp2 = round(entry_price - (atr_value * self.atr_tp2_multiplier), 2)
            tp3 = round(entry_price - (atr_value * self.atr_tp3_multiplier), 2)
        
        take_profits = [TakeProfitLevel(price=tp1, percentage=tp1_pct)]
        
        if tp_count >= 2 and tp2_pct > 0:
            take_profits.append(TakeProfitLevel(price=tp2, percentage=tp2_pct))
        
        if tp_count >= 3 and tp3_pct > 0:
            take_profits.append(TakeProfitLevel(price=tp3, percentage=tp3_pct))
        
        return take_profits, stop_loss
    
    def _get_tp_config(self) -> Tuple[int, int, int, int]:
        """Get TP configuration from database"""
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                tp_count = int(config.get('tp_count', 3))
                tp1_pct = int(config.get('tp1_percentage', 50))
                tp2_pct = int(config.get('tp2_percentage', 30))
                tp3_pct = int(config.get('tp3_percentage', 20))
                return tp1_pct, tp2_pct, tp3_pct, tp_count
        except Exception as e:
            logger.error(f"Error loading TP config: {e}")
        
        return 50, 30, 20, 3
    
    async def check_for_signals(self, timeframe: str = '15min') -> Optional[SignalData]:
        try:
            self.load_config()
            
            logger.info(f"Checking for signals on {self.symbol} {timeframe}...")
            
            can_generate, guardrail_reason = self.check_guardrails()
            if not can_generate:
                logger.info(f"Guardrail blocked: {guardrail_reason}")
                return None
            
            price = twelve_data_client.get_price(self.symbol)
            rsi = twelve_data_client.get_rsi(self.symbol, timeframe)
            macd_data = twelve_data_client.get_macd(self.symbol, timeframe)
            atr = twelve_data_client.get_atr(self.symbol, timeframe)
            adx = twelve_data_client.get_adx(self.symbol, timeframe)
            bbands = twelve_data_client.get_bbands(self.symbol, timeframe)
            stoch = twelve_data_client.get_stoch(self.symbol, timeframe)
            ema50 = twelve_data_client.get_ema(self.symbol, '1h', 50)
            ema200 = twelve_data_client.get_ema(self.symbol, '1h', 200)
            
            if not all([price, rsi, macd_data, atr, adx, bbands, stoch, ema50, ema200]):
                logger.warning("Missing indicator data, skipping signal check")
                return None
            
            assert price is not None
            assert rsi is not None
            assert macd_data is not None
            assert atr is not None
            assert adx is not None
            assert bbands is not None
            assert stoch is not None
            assert ema50 is not None
            assert ema200 is not None
            
            logger.info(f"Price: {price:.2f}, RSI: {rsi:.2f}, MACD: {macd_data['macd']:.4f}, ADX: {adx:.2f}")
            
            trend_is_bullish = ema50 > ema200
            trend_name = "Bullish" if trend_is_bullish else "Bearish"
            
            if adx < self.adx_threshold:
                logger.info(f"Weak trend - ADX {adx:.2f} < {self.adx_threshold}")
                return None
            
            signal_type = None
            
            if rsi < self.rsi_oversold:
                bb_distance = abs(price - bbands['lower'])
                bb_touch = bb_distance < (atr * 0.5)
                stoch_oversold = stoch['is_oversold']
                
                if bb_touch or stoch_oversold:
                    signal_type = 'BUY'
                    logger.info(f"📈 BUY signal - Trend={trend_name}, RSI={rsi:.2f}, ADX={adx:.2f}")
            
            elif rsi > self.rsi_overbought:
                bb_distance = abs(price - bbands['upper'])
                bb_touch = bb_distance < (atr * 0.5)
                stoch_overbought = stoch['is_overbought']
                
                if bb_touch or stoch_overbought:
                    signal_type = 'SELL'
                    logger.info(f"📉 SELL signal - Trend={trend_name}, RSI={rsi:.2f}, ADX={adx:.2f}")
            
            if not signal_type:
                logger.info(f"No signal - RSI={rsi:.2f} (thresholds: {self.rsi_oversold}/{self.rsi_overbought})")
                return None
            
            take_profits, stop_loss = self.calculate_tp_sl(price, atr, signal_type)
            
            indicators = {
                'rsi': rsi,
                'macd': macd_data['macd'],
                'adx': adx,
                'stochastic': stoch['k'],
                'atr': atr,
                'bollinger_middle': bbands['middle'],
                'bollinger_upper': bbands['upper'],
                'bollinger_lower': bbands['lower'],
                'ema50': ema50,
                'ema200': ema200
            }
            
            signal_data = SignalData(
                signal_type=signal_type,
                pair=self.symbol,
                timeframe=timeframe,
                entry_price=price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                indicators=indicators,
                bot_type=self.bot_type
            )
            
            logger.info(f"🎯 Signal generated: {signal_type} @ {price:.2f}")
            logger.info(f"📊 TP1: {take_profits[0].price:.2f} (50%), TP2: {take_profits[1].price:.2f} (30%), TP3: {take_profits[2].price:.2f} (20%)")
            logger.info(f"🛑 SL: {stop_loss:.2f}")
            
            return signal_data
            
        except Exception as e:
            logger.exception(f"Error checking for signals: {e}")
            return None
    
    def get_indicators_used(self) -> List[str]:
        return ['RSI(30/70)', 'MACD', 'Bollinger Bands', 'Stochastic', 'ADX', 'EMA(50/200)']
