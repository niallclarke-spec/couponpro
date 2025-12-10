"""
Raja Banks Gold Start Strategy
Impulse Entry Breakout with Session-Based Trading

Based on Roger Banks' trading methodology:
- Wait for session open (London, NY, Overlap)
- Detect impulse breakouts on 15M candles
- Tight stop loss placement (above/below current candle)
- Target wick fill for take profit
- Hybrid trend filter (with trend + counter-trend at S/R zones)
"""
from typing import Dict, List, Optional, Tuple
from strategies.base_strategy import BaseStrategy, SignalData, TakeProfitLevel
from forex_api import twelve_data_client
from db import get_forex_config, get_daily_pnl, count_signals_today_by_bot, get_last_signal_time_by_bot
from datetime import datetime, timedelta


class RajaBanksStrategy(BaseStrategy):
    name = "Raja Banks Gold Start"
    description = "Impulse entry breakout strategy. Trades session opens with tight stops and wick-fill targets. 4 signals/day max with 15-min cooldown."
    bot_type = "raja_banks"
    
    tp_levels = 2
    tp_percentages = [70, 30]
    
    breakeven_threshold = 60.0
    
    LONDON_START = 7
    LONDON_END = 10
    NY_START = 12
    NY_END = 16
    OVERLAP_START = 13
    OVERLAP_END = 16
    
    MAX_SIGNALS_PER_DAY = 4
    COOLDOWN_MINUTES = 15
    
    def __init__(self):
        super().__init__()
        self.load_config()
    
    def load_config(self):
        try:
            config = get_forex_config()
            if config:
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 1.5)
                self.daily_loss_cap_pips = float(config.get('daily_loss_cap_pips', 50.0))
            else:
                self._set_defaults()
        except Exception as e:
            print(f"[RAJA_BANKS] Error loading config: {e}")
            self._set_defaults()
    
    def _set_defaults(self):
        self.atr_sl_multiplier = 1.5
        self.daily_loss_cap_pips = 50.0
    
    def is_in_session(self) -> Tuple[bool, str]:
        """Check if current time is within a trading session"""
        now = datetime.utcnow()
        current_hour = now.hour
        
        if self.LONDON_START <= current_hour < self.LONDON_END:
            return True, "London"
        
        if self.NY_START <= current_hour < self.NY_END:
            if self.OVERLAP_START <= current_hour < self.OVERLAP_END:
                return True, "London/NY Overlap"
            return True, "New York"
        
        return False, "Off-hours"
    
    def check_cooldown(self) -> Tuple[bool, Optional[str]]:
        """Check if enough time has passed since last signal (using database)"""
        last_signal_time = get_last_signal_time_by_bot(self.bot_type)
        
        if last_signal_time is None:
            return True, None
        
        now = datetime.utcnow()
        if last_signal_time.tzinfo:
            last_signal_time = last_signal_time.replace(tzinfo=None)
        
        time_since_last = (now - last_signal_time).total_seconds() / 60
        
        if time_since_last < self.COOLDOWN_MINUTES:
            remaining = int(self.COOLDOWN_MINUTES - time_since_last)
            return False, f"Cooldown active ({remaining}min remaining)"
        
        return True, None
    
    def check_daily_limit(self) -> Tuple[bool, Optional[str]]:
        """Check if daily signal limit has been reached (using database)"""
        signals_today = count_signals_today_by_bot(self.bot_type)
        
        if signals_today >= self.MAX_SIGNALS_PER_DAY:
            return False, f"Daily limit reached ({signals_today}/{self.MAX_SIGNALS_PER_DAY} signals)"
        
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
        
        daily_pnl = get_daily_pnl()
        if daily_pnl <= -self.daily_loss_cap_pips:
            return False, f"Daily loss cap reached ({daily_pnl:.1f} pips)"
        
        return True, None
    
    def detect_impulse_break(self, candles: List[Dict]) -> Optional[Dict]:
        """
        Detect impulse breakout pattern
        
        Returns:
            Dict with signal info or None if no valid setup
        """
        if not candles or len(candles) < 3:
            return None
        
        current = candles[0]
        previous = candles[1]
        before_prev = candles[2]
        
        current_high = current['high']
        current_low = current['low']
        current_close = current['close']
        
        prev_high = previous['high']
        prev_low = previous['low']
        
        is_bearish_break = current_close < prev_low and current_low < prev_low
        is_bullish_break = current_close > prev_high and current_high > prev_high
        
        if is_bearish_break:
            wick_to_fill = None
            for i in range(1, min(5, len(candles))):
                candle = candles[i]
                if candle['low'] < current_low:
                    wick_to_fill = candle['low']
                    break
            
            return {
                'signal_type': 'SELL',
                'entry_price': current_close,
                'stop_loss': current_high,
                'wick_target': wick_to_fill,
                'break_candle': current,
                'reference_candle': previous
            }
        
        elif is_bullish_break:
            wick_to_fill = None
            for i in range(1, min(5, len(candles))):
                candle = candles[i]
                if candle['high'] > current_high:
                    wick_to_fill = candle['high']
                    break
            
            return {
                'signal_type': 'BUY',
                'entry_price': current_close,
                'stop_loss': current_low,
                'wick_target': wick_to_fill,
                'break_candle': current,
                'reference_candle': previous
            }
        
        return None
    
    def validate_with_trend(self, signal_type: str, ema50: float, ema200: float, sr_data: Optional[Dict]) -> Tuple[bool, str]:
        """
        Validate signal using hybrid trend filter
        
        With-trend signals: Always allowed
        Counter-trend signals: Only at S/R zones
        """
        trend_is_bullish = ema50 > ema200
        trend_name = "Bullish" if trend_is_bullish else "Bearish"
        
        if signal_type == 'BUY' and trend_is_bullish:
            return True, f"With-trend BUY ({trend_name})"
        
        if signal_type == 'SELL' and not trend_is_bullish:
            return True, f"With-trend SELL ({trend_name})"
        
        if sr_data:
            current_price = sr_data.get('current_price', 0)
            resistance = sr_data.get('resistance')
            support = sr_data.get('support')
            
            if signal_type == 'SELL' and trend_is_bullish:
                if resistance and abs(current_price - resistance) < 5:
                    return True, f"Counter-trend SELL at resistance ({resistance:.2f})"
            
            if signal_type == 'BUY' and not trend_is_bullish:
                if support and abs(current_price - support) < 5:
                    return True, f"Counter-trend BUY at support ({support:.2f})"
        
        return False, f"Counter-trend {signal_type} rejected (no S/R confluence)"
    
    def calculate_tp_sl(self, entry_price: float, atr_value: float, signal_type: str, 
                        wick_target: Optional[float] = None) -> Tuple[List[TakeProfitLevel], float]:
        """Calculate TP/SL with wick-fill targeting"""
        tp1_pct, tp2_pct, tp3_pct, tp_count = self._get_tp_config()
        
        if signal_type == 'BUY':
            if wick_target and wick_target > entry_price:
                tp1 = round(wick_target, 2)
            else:
                tp1 = round(entry_price + (atr_value * 1.5), 2)
            
            tp2 = round(entry_price + (atr_value * 2.5), 2)
            tp3 = round(entry_price + (atr_value * 3.5), 2)
            stop_loss = round(entry_price - (atr_value * self.atr_sl_multiplier), 2)
        else:
            if wick_target and wick_target < entry_price:
                tp1 = round(wick_target, 2)
            else:
                tp1 = round(entry_price - (atr_value * 1.5), 2)
            
            tp2 = round(entry_price - (atr_value * 2.5), 2)
            tp3 = round(entry_price - (atr_value * 3.5), 2)
            stop_loss = round(entry_price + (atr_value * self.atr_sl_multiplier), 2)
        
        take_profits = [TakeProfitLevel(price=tp1, percentage=tp1_pct)]
        
        if tp_count >= 2 and tp2_pct > 0:
            take_profits.append(TakeProfitLevel(price=tp2, percentage=tp2_pct))
        
        if tp_count >= 3 and tp3_pct > 0:
            take_profits.append(TakeProfitLevel(price=tp3, percentage=tp3_pct))
        
        return take_profits, stop_loss
    
    def _get_tp_config(self) -> Tuple[int, int, int, int]:
        """Get TP configuration from database"""
        try:
            config = get_forex_config()
            if config:
                tp_count = int(config.get('tp_count', 3))
                tp1_pct = int(config.get('tp1_percentage', 50))
                tp2_pct = int(config.get('tp2_percentage', 30))
                tp3_pct = int(config.get('tp3_percentage', 20))
                return tp1_pct, tp2_pct, tp3_pct, tp_count
        except Exception as e:
            print(f"[RAJA_BANKS] Error loading TP config: {e}")
        
        return 50, 30, 20, 3
    
    async def check_for_signals(self, timeframe: str = '15min') -> Optional[SignalData]:
        try:
            self.load_config()
            
            print(f"\n[RAJA_BANKS] Checking for signals on {self.symbol} {timeframe}...")
            
            can_generate, guardrail_reason = self.check_guardrails()
            if not can_generate:
                print(f"[RAJA_BANKS] Guardrail blocked: {guardrail_reason}")
                return None
            
            in_session, session_name = self.is_in_session()
            print(f"[RAJA_BANKS] Session: {session_name}")
            
            candles = twelve_data_client.get_time_series(self.symbol, timeframe, 10)
            if not candles or len(candles) < 3:
                print("[RAJA_BANKS] Insufficient candle data")
                return None
            
            ema50 = twelve_data_client.get_ema(self.symbol, '1h', 50)
            ema200 = twelve_data_client.get_ema(self.symbol, '1h', 200)
            atr = twelve_data_client.get_atr(self.symbol, timeframe)
            
            if not all([ema50, ema200, atr]):
                print("[RAJA_BANKS] Missing indicator data")
                return None
            
            assert ema50 is not None
            assert ema200 is not None
            assert atr is not None
            
            sr_data = twelve_data_client.get_support_resistance(self.symbol, '1h', 20)
            
            impulse = self.detect_impulse_break(candles)
            
            if not impulse:
                print("[RAJA_BANKS] No impulse breakout detected")
                return None
            
            signal_type = impulse['signal_type']
            entry_price = impulse['entry_price']
            candle_stop = impulse['stop_loss']
            wick_target = impulse.get('wick_target')
            
            is_valid, trend_reason = self.validate_with_trend(signal_type, ema50, ema200, sr_data)
            
            if not is_valid:
                print(f"[RAJA_BANKS] {trend_reason}")
                return None
            
            print(f"[RAJA_BANKS] {trend_reason}")
            
            take_profits, calculated_sl = self.calculate_tp_sl(
                entry_price, atr, signal_type, wick_target
            )
            
            if signal_type == 'BUY':
                stop_loss = max(candle_stop, calculated_sl)
            else:
                stop_loss = min(candle_stop, calculated_sl)
            
            indicators = {
                'ema50': ema50,
                'ema200': ema200,
                'atr': atr,
                'session': session_name,
                'impulse_type': 'breakout',
                'candle_high': candles[0]['high'],
                'candle_low': candles[0]['low'],
                'wick_target': wick_target,
                'support': sr_data.get('support') if sr_data else None,
                'resistance': sr_data.get('resistance') if sr_data else None
            }
            
            signal_data = SignalData(
                signal_type=signal_type,
                pair=self.symbol,
                timeframe=timeframe,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                indicators=indicators,
                bot_type=self.bot_type
            )
            
            signals_today = count_signals_today_by_bot(self.bot_type)
            
            print(f"[RAJA_BANKS] Signal generated: {signal_type} @ {entry_price:.2f}")
            print(f"[RAJA_BANKS] TP1: {take_profits[0].price:.2f} ({take_profits[0].percentage}%)")
            if len(take_profits) > 1:
                print(f"[RAJA_BANKS] TP2: {take_profits[1].price:.2f} ({take_profits[1].percentage}%)")
            print(f"[RAJA_BANKS] SL: {stop_loss:.2f} (tight candle-based)")
            print(f"[RAJA_BANKS] Signals today: {signals_today + 1}/{self.MAX_SIGNALS_PER_DAY}")
            
            return signal_data
            
        except Exception as e:
            print(f"[RAJA_BANKS] Error checking for signals: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_indicators_used(self) -> List[str]:
        return ['EMA(50/200)', 'ATR', 'Candle Breakout', 'Support/Resistance', 'Session Filter']
    
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
            'max_signals_per_day': self.MAX_SIGNALS_PER_DAY,
            'cooldown_minutes': self.COOLDOWN_MINUTES,
            'sessions': ['London (07:00-10:00)', 'New York (12:00-16:00)', 'Overlap (13:00-16:00)']
        }
