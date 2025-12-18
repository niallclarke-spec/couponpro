"""
Trend Pullback Strategy
Multi-timeframe trend pullback strategy with 1H EMA200 filter, 15M pullback entries, and 3-level take profits.

Entry Modes:
- Mode A (primary): Trend pullback entry - RSI dip/recovery near EMA20 in established trend
- Mode B (optional): Bollinger squeeze breakout - disabled by default
"""
from typing import Dict, List, Optional, Tuple
from strategies.base_strategy import BaseStrategy, SignalData, TakeProfitLevel
from forex_api import twelve_data_client
from db import get_forex_config, get_daily_pnl, count_signals_today_by_bot, get_last_signal_time_by_bot
from datetime import datetime
from core.logging import get_logger

logger = get_logger(__name__)


class TrendPullbackStrategy(BaseStrategy):
    name = "Trend Pullback"
    description = "Multi-timeframe trend pullback strategy with 1H EMA200 filter, 15M pullback entries, and 3-level take profits."
    bot_type = "trend_pullback_multi_tp"
    
    tp_levels = 3
    tp_percentages = [40, 30, 30]
    
    breakeven_threshold = 60.0
    
    MAX_SIGNALS_PER_DAY = 5
    COOLDOWN_MINUTES = 20
    
    def __init__(self, tenant_id: Optional[str] = None):
        super().__init__(tenant_id=tenant_id)
        self.load_config()
    
    def load_config(self):
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.session_start_hour = int(config.get('session_start_hour', 7))
                self.session_end_hour = int(config.get('session_end_hour', 17))
                self.adx_min = float(config.get('adx_min', 20))
                self.atr_mult = float(config.get('atr_mult', 1.2))
                self.swing_lookback = int(config.get('swing_lookback', 8))
                self.ema200_slope_bars = int(config.get('ema200_slope_bars', 5))
                self.pullback_ema_tolerance = float(config.get('pullback_ema_tolerance', 0.3))
                self.min_stop_usd = float(config.get('min_stop_usd', 2.0))
                self.be_buffer_r = float(config.get('be_buffer_r', 0.1))
                squeeze_enabled = config.get('squeeze_enabled', False)
                self.squeeze_enabled = str(squeeze_enabled).lower() == 'true' if isinstance(squeeze_enabled, str) else bool(squeeze_enabled)
                self.squeeze_percentile = int(config.get('squeeze_percentile', 10))
                self.atr_max = config.get('atr_max')
                if self.atr_max is not None:
                    self.atr_max = float(self.atr_max)
                self.candle_range_atr_block = float(config.get('candle_range_atr_block', 2.5))
                self.tp1_pct = int(config.get('tp1_pct', 40))
                self.tp2_pct = int(config.get('tp2_pct', 30))
                self.tp3_pct = int(config.get('tp3_pct', 30))
                self.daily_loss_cap_pips = float(config.get('daily_loss_cap_pips', 50.0))
                self.max_signals_per_day = int(config.get('max_signals_per_day', 5))
                self.cooldown_minutes = int(config.get('cooldown_minutes', 20))
            else:
                self._set_defaults()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._set_defaults()
    
    def _set_defaults(self):
        self.session_start_hour = 7
        self.session_end_hour = 17
        self.adx_min = 20
        self.atr_mult = 1.2
        self.swing_lookback = 8
        self.ema200_slope_bars = 5
        self.pullback_ema_tolerance = 0.3
        self.min_stop_usd = 2.0
        self.be_buffer_r = 0.1
        self.squeeze_enabled = False
        self.squeeze_percentile = 10
        self.atr_max = None
        self.candle_range_atr_block = 2.5
        self.tp1_pct = 40
        self.tp2_pct = 30
        self.tp3_pct = 30
        self.daily_loss_cap_pips = 50.0
        self.max_signals_per_day = 5
        self.cooldown_minutes = 20
    
    def is_in_session(self) -> Tuple[bool, str]:
        """Check if current time is within trading session"""
        now = datetime.utcnow()
        current_hour = now.hour
        
        if self.session_start_hour <= current_hour < self.session_end_hour:
            return True, f"Active ({self.session_start_hour}:00-{self.session_end_hour}:00 UTC)"
        
        return False, f"Off-hours (session: {self.session_start_hour}:00-{self.session_end_hour}:00 UTC)"
    
    def check_cooldown(self) -> Tuple[bool, Optional[str]]:
        """Check if enough time has passed since last signal"""
        last_signal_time = get_last_signal_time_by_bot(self.bot_type, tenant_id=self.tenant_id)
        
        if last_signal_time is None:
            return True, None
        
        now = datetime.utcnow()
        if last_signal_time.tzinfo:
            last_signal_time = last_signal_time.replace(tzinfo=None)
        
        time_since_last = (now - last_signal_time).total_seconds() / 60
        
        if time_since_last < self.cooldown_minutes:
            remaining = int(self.cooldown_minutes - time_since_last)
            return False, f"Cooldown active ({remaining}min remaining)"
        
        return True, None
    
    def check_daily_limit(self) -> Tuple[bool, Optional[str]]:
        """Check if daily signal limit has been reached"""
        signals_today = count_signals_today_by_bot(self.bot_type, tenant_id=self.tenant_id)
        
        if signals_today >= self.max_signals_per_day:
            return False, f"Daily limit reached ({signals_today}/{self.max_signals_per_day} signals)"
        
        return True, None
    
    def check_guardrails(self) -> Tuple[bool, Optional[str]]:
        """Check all trading guardrails"""
        in_session, session_name = self.is_in_session()
        if not in_session:
            return False, f"Outside trading session ({session_name})"
        
        can_trade, cooldown_msg = self.check_cooldown()
        if not can_trade:
            return False, cooldown_msg
        
        can_trade, limit_msg = self.check_daily_limit()
        if not can_trade:
            return False, limit_msg
        
        daily_pnl = get_daily_pnl(tenant_id=self.tenant_id)
        if daily_pnl <= -self.daily_loss_cap_pips:
            return False, f"Daily loss cap reached ({daily_pnl:.1f} pips)"
        
        return True, None
    
    def check_volatility_gate(self, atr: float, candle_high: float, candle_low: float) -> Tuple[bool, Optional[str]]:
        """Volatility sanity gate - must pass before entry"""
        if self.atr_max is not None and atr > self.atr_max:
            return False, f"ATR too high ({atr:.2f} > {self.atr_max})"
        
        candle_range = candle_high - candle_low
        max_allowed_range = self.candle_range_atr_block * atr
        
        if candle_range > max_allowed_range:
            return False, f"Candle range too large ({candle_range:.2f} > {max_allowed_range:.2f})"
        
        return True, None
    
    def check_ema200_slope(self, ema200_series: List[float], current_price: float) -> Tuple[bool, str]:
        """Check if EMA200 has positive/negative slope using actual EMA values"""
        if not ema200_series or len(ema200_series) < self.ema200_slope_bars + 1:
            return False, "Insufficient EMA200 data for slope calculation"
        
        current_ema = ema200_series[0]
        old_ema = ema200_series[self.ema200_slope_bars]
        
        slope = current_ema - old_ema
        
        if slope > 0 and current_price > current_ema:
            return True, "bullish"
        elif slope < 0 and current_price < current_ema:
            return True, "bearish"
        else:
            return False, "flat or counter-trend"
    
    def detect_rsi_recovery(self, rsi_series: List[float]) -> Tuple[bool, str]:
        """Detect RSI dip into [38-48] and recovery above 50 for LONG"""
        if not rsi_series or len(rsi_series) < 2:
            return False, "Insufficient RSI history"
        
        current_rsi = rsi_series[0]
        
        was_in_dip = any(38 <= r <= 48 for r in rsi_series[1:])
        
        if was_in_dip and current_rsi > 50:
            return True, f"RSI dip-recovery confirmed ({current_rsi:.2f})"
        elif 38 <= current_rsi <= 48:
            return False, f"RSI still in dip zone ({current_rsi:.2f})"
        elif current_rsi > 50 and not was_in_dip:
            return False, f"No prior dip detected ({current_rsi:.2f})"
        else:
            return False, f"RSI conditions not met ({current_rsi:.2f})"
    
    def detect_rsi_recovery_short(self, rsi_series: List[float]) -> Tuple[bool, str]:
        """Detect RSI spike into [52-62] and recovery below 50 for SHORT"""
        if not rsi_series or len(rsi_series) < 2:
            return False, "Insufficient RSI history"
        
        current_rsi = rsi_series[0]
        
        was_in_spike = any(52 <= r <= 62 for r in rsi_series[1:])
        
        if was_in_spike and current_rsi < 50:
            return True, f"RSI spike-recovery confirmed ({current_rsi:.2f})"
        elif 52 <= current_rsi <= 62:
            return False, f"RSI still in spike zone ({current_rsi:.2f})"
        elif current_rsi < 50 and not was_in_spike:
            return False, f"No prior spike detected ({current_rsi:.2f})"
        else:
            return False, f"RSI conditions not met ({current_rsi:.2f})"
    
    def detect_trigger_candle(self, candles: List[Dict], signal_type: str) -> Tuple[bool, str]:
        """Detect trigger: close > prev high (BUY) or close < prev low (SELL), or engulfing"""
        if len(candles) < 2:
            return False, "Insufficient candle data"
        
        current = candles[0]
        previous = candles[1]
        
        current_open = current['open']
        current_close = current['close']
        current_high = current['high']
        current_low = current['low']
        
        prev_open = previous['open']
        prev_close = previous['close']
        prev_high = previous['high']
        prev_low = previous['low']
        
        if signal_type == 'BUY':
            break_trigger = current_close > prev_high
            bullish_engulfing = (prev_close < prev_open and 
                                 current_close > current_open and 
                                 current_close > prev_open and 
                                 current_open < prev_close)
            
            if break_trigger:
                return True, "Close > prev high"
            elif bullish_engulfing:
                return True, "Bullish engulfing"
            return False, "No bullish trigger"
        
        else:
            break_trigger = current_close < prev_low
            bearish_engulfing = (prev_close > prev_open and 
                                 current_close < current_open and 
                                 current_close < prev_open and 
                                 current_open > prev_close)
            
            if break_trigger:
                return True, "Close < prev low"
            elif bearish_engulfing:
                return True, "Bearish engulfing"
            return False, "No bearish trigger"
    
    def detect_bollinger_squeeze(self, bbands_series: List[Dict], adx: float, price: float) -> Tuple[bool, str, Optional[str]]:
        """Detect Bollinger squeeze using percentile-based width comparison"""
        if not self.squeeze_enabled:
            return False, "Squeeze mode disabled", None
        
        if not bbands_series or len(bbands_series) < 10:
            return False, "Insufficient BB history for squeeze detection", None
        
        widths = [bb['upper'] - bb['lower'] for bb in bbands_series]
        current_width = widths[0]
        
        sorted_widths = sorted(widths)
        threshold_idx = max(0, int(len(sorted_widths) * self.squeeze_percentile / 100) - 1)
        squeeze_threshold = sorted_widths[threshold_idx]
        
        is_squeeze = current_width <= squeeze_threshold
        
        if not is_squeeze:
            return False, f"No squeeze (width {current_width:.2f} > {squeeze_threshold:.2f})", None
        
        if adx < self.adx_min:
            return False, f"Squeeze detected but ADX too low ({adx:.2f})", None
        
        current_bb = bbands_series[0]
        if price > current_bb['upper']:
            return True, "Squeeze breakout UP", "BUY"
        elif price < current_bb['lower']:
            return True, "Squeeze breakout DOWN", "SELL"
        
        return False, "Squeeze active, no breakout yet", None
    
    def calculate_swing_stop(self, candles: List[Dict], signal_type: str) -> float:
        """Calculate swing-based stop loss"""
        lookback_candles = candles[:self.swing_lookback] if len(candles) >= self.swing_lookback else candles
        
        if signal_type == 'BUY':
            swing_stop = min(c['low'] for c in lookback_candles)
        else:
            swing_stop = max(c['high'] for c in lookback_candles)
        
        return swing_stop
    
    def calculate_tp_sl(self, entry_price: float, atr_value: float, signal_type: str,
                        candles: Optional[List[Dict]] = None) -> Tuple[List[TakeProfitLevel], float]:
        """Calculate TP/SL using R-based approach"""
        swing_stop = None
        if candles:
            swing_stop = self.calculate_swing_stop(candles, signal_type)
        
        atr_stop_distance = atr_value * self.atr_mult
        
        if signal_type == 'BUY':
            if swing_stop:
                swing_stop_distance = entry_price - swing_stop
                sl_distance = min(swing_stop_distance, atr_stop_distance)
            else:
                sl_distance = atr_stop_distance
            
            sl_distance = max(sl_distance, self.min_stop_usd)
            stop_loss = round(entry_price - sl_distance, 2)
        else:
            if swing_stop:
                swing_stop_distance = swing_stop - entry_price
                sl_distance = min(swing_stop_distance, atr_stop_distance)
            else:
                sl_distance = atr_stop_distance
            
            sl_distance = max(sl_distance, self.min_stop_usd)
            stop_loss = round(entry_price + sl_distance, 2)
        
        r_value = sl_distance
        
        if signal_type == 'BUY':
            tp1 = round(entry_price + (1.0 * r_value), 2)
            tp2 = round(entry_price + (2.0 * r_value), 2)
            tp3 = round(entry_price + (3.0 * r_value), 2)
        else:
            tp1 = round(entry_price - (1.0 * r_value), 2)
            tp2 = round(entry_price - (2.0 * r_value), 2)
            tp3 = round(entry_price - (3.0 * r_value), 2)
        
        take_profits = [
            TakeProfitLevel(price=tp1, percentage=self.tp1_pct),
            TakeProfitLevel(price=tp2, percentage=self.tp2_pct),
            TakeProfitLevel(price=tp3, percentage=self.tp3_pct)
        ]
        
        return take_profits, stop_loss
    
    def check_pullback_entry(self, price: float, ema20: float, ema200_series: List[float],
                             adx: float, rsi_series: List[float], atr: float,
                             candles_15m: List[Dict]) -> Optional[Dict]:
        """Check for Mode A: Trend Pullback Entry"""
        has_slope, slope_direction = self.check_ema200_slope(ema200_series, price)
        
        if not has_slope:
            return None
        
        current_ema200 = ema200_series[0] if ema200_series else None
        if current_ema200 is None:
            return None
        
        pullback_tolerance = self.pullback_ema_tolerance * atr
        near_ema20 = abs(price - ema20) <= pullback_tolerance
        
        if not near_ema20:
            return None
        
        if adx < self.adx_min:
            return None
        
        if slope_direction == "bullish" and price > current_ema200:
            rsi_ok, rsi_msg = self.detect_rsi_recovery(rsi_series)
            if not rsi_ok:
                return None
            
            trigger_ok, trigger_msg = self.detect_trigger_candle(candles_15m, 'BUY')
            if not trigger_ok:
                return None
            
            return {
                'signal_type': 'BUY',
                'mode': 'pullback',
                'slope': slope_direction,
                'rsi_reason': rsi_msg,
                'trigger_reason': trigger_msg
            }
        
        elif slope_direction == "bearish" and price < current_ema200:
            rsi_ok, rsi_msg = self.detect_rsi_recovery_short(rsi_series)
            if not rsi_ok:
                return None
            
            trigger_ok, trigger_msg = self.detect_trigger_candle(candles_15m, 'SELL')
            if not trigger_ok:
                return None
            
            return {
                'signal_type': 'SELL',
                'mode': 'pullback',
                'slope': slope_direction,
                'rsi_reason': rsi_msg,
                'trigger_reason': trigger_msg
            }
        
        return None
    
    def check_squeeze_entry(self, price: float, bbands_series: List[Dict], adx: float,
                            candles_15m: List[Dict]) -> Optional[Dict]:
        """Check for Mode B: Bollinger Squeeze Breakout (optional)"""
        if not self.squeeze_enabled:
            return None
        
        squeeze_ok, squeeze_msg, signal_type = self.detect_bollinger_squeeze(bbands_series, adx, price)
        
        if not squeeze_ok or signal_type is None:
            return None
        
        trigger_ok, trigger_msg = self.detect_trigger_candle(candles_15m, signal_type)
        if trigger_ok:
            return {
                'signal_type': signal_type,
                'mode': 'squeeze',
                'trigger_reason': f"{squeeze_msg} + {trigger_msg}"
            }
        
        return None
    
    async def check_for_signals(self, timeframe: str = '15min') -> Optional[SignalData]:
        try:
            self.load_config()
            
            logger.info(f"[{self.bot_type}] Checking for signals on {self.symbol} {timeframe}...")
            
            can_generate, guardrail_reason = self.check_guardrails()
            if not can_generate:
                logger.info(f"[{self.bot_type}] Guardrail blocked: {guardrail_reason}")
                return None
            
            ema200_series = twelve_data_client.get_ema_series(self.symbol, '1h', 200, self.ema200_slope_bars + 1)
            ema20_15m = twelve_data_client.get_ema(self.symbol, '15min', 20)
            rsi_series = twelve_data_client.get_rsi_series(self.symbol, '15min', 14, 5)
            adx = twelve_data_client.get_adx(self.symbol, '15min')
            atr = twelve_data_client.get_atr(self.symbol, '15min')
            bbands = twelve_data_client.get_bbands(self.symbol, '15min')
            candles_15m = twelve_data_client.get_time_series(self.symbol, '15min', 20)
            
            bbands_series = None
            if self.squeeze_enabled:
                bbands_series = twelve_data_client.get_bbands_series(self.symbol, '15min', 20, 20)
            
            if not all([ema200_series, ema20_15m, rsi_series, adx, atr, bbands, candles_15m]):
                logger.warning(f"[{self.bot_type}] Missing indicator data, skipping signal check")
                return None
            
            assert ema200_series is not None
            assert ema20_15m is not None
            assert rsi_series is not None
            assert adx is not None
            assert atr is not None
            assert bbands is not None
            assert candles_15m is not None
            
            current_candle = candles_15m[0]
            price = current_candle['close']
            
            ema200_1h = ema200_series[0]
            rsi = rsi_series[0]
            
            vol_ok, vol_msg = self.check_volatility_gate(atr, current_candle['high'], current_candle['low'])
            if not vol_ok:
                logger.info(f"[{self.bot_type}] Volatility gate blocked: {vol_msg}")
                return None
            
            logger.info(f"[{self.bot_type}] Price: {price:.2f}, EMA200(1H): {ema200_1h:.2f}, "
                       f"EMA20(15M): {ema20_15m:.2f}, RSI: {rsi:.2f}, ADX: {adx:.2f}, ATR: {atr:.2f}")
            
            entry_result = self.check_pullback_entry(
                price, ema20_15m, ema200_series, adx, rsi_series, atr, candles_15m
            )
            
            if not entry_result and self.squeeze_enabled and bbands_series:
                entry_result = self.check_squeeze_entry(price, bbands_series, adx, candles_15m)
            
            if not entry_result:
                logger.info(f"[{self.bot_type}] No valid entry conditions met")
                return None
            
            signal_type = entry_result['signal_type']
            mode = entry_result['mode']
            
            take_profits, stop_loss = self.calculate_tp_sl(price, atr, signal_type, candles_15m)
            
            r_value = abs(price - stop_loss)
            
            indicators = {
                'ema200_1h': ema200_1h,
                'ema20_15m': ema20_15m,
                'rsi': rsi,
                'adx': adx,
                'atr': atr,
                'bollinger_upper': bbands['upper'],
                'bollinger_middle': bbands['middle'],
                'bollinger_lower': bbands['lower'],
                'mode': mode,
                'tp1_allocation': self.tp1_pct / 100,
                'tp2_allocation': self.tp2_pct / 100,
                'tp3_allocation': self.tp3_pct / 100,
                'be_buffer_r': self.be_buffer_r,
                'r_value': r_value,
                'entry_reason': entry_result.get('trigger_reason', ''),
                'slope': entry_result.get('slope', ''),
                'session': f"{self.session_start_hour}:00-{self.session_end_hour}:00 UTC"
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
            
            signals_today = count_signals_today_by_bot(self.bot_type, tenant_id=self.tenant_id)
            
            logger.info(f"[{self.bot_type}] 🎯 Signal generated: {signal_type} @ {price:.2f} (mode: {mode})")
            logger.info(f"[{self.bot_type}] 📊 TP1: {take_profits[0].price:.2f} ({take_profits[0].percentage}%), "
                       f"TP2: {take_profits[1].price:.2f} ({take_profits[1].percentage}%), "
                       f"TP3: {take_profits[2].price:.2f} ({take_profits[2].percentage}%)")
            logger.info(f"[{self.bot_type}] 🛑 SL: {stop_loss:.2f} (R: {r_value:.2f})")
            logger.info(f"[{self.bot_type}] 📈 Signals today: {signals_today + 1}/{self.max_signals_per_day}")
            
            return signal_data
            
        except Exception as e:
            logger.exception(f"[{self.bot_type}] Error checking for signals: {e}")
            return None
    
    def get_indicators_used(self) -> List[str]:
        return ['EMA(200) 1H', 'EMA(20) 15M', 'RSI(14)', 'ADX(14)', 'ATR(14)', 'Bollinger Bands', 'Swing S/R']
    
    def get_display_info(self) -> Dict:
        """Return display information for the admin panel"""
        return {
            'name': self.name,
            'description': self.description,
            'bot_type': self.bot_type,
            'indicators': self.get_indicators_used(),
            'tp_levels': self.tp_levels,
            'tp_percentages': self.tp_percentages,
            'breakeven_threshold': self.breakeven_threshold,
            'max_signals_per_day': self.max_signals_per_day,
            'cooldown_minutes': self.cooldown_minutes,
            'sessions': [f'{self.session_start_hour}:00-{self.session_end_hour}:00 UTC'],
            'modes': ['pullback (primary)', 'squeeze (optional)']
        }
