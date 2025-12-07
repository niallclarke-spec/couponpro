"""
Forex signal generation engine
Combines RSI + MACD + ATR for XAU/USD trading signals
"""
import os
import asyncio
from datetime import datetime, timedelta
from forex_api import twelve_data_client
from db import create_forex_signal, get_forex_signals, update_forex_signal_status, get_forex_config
from indicator_config import (
    get_validation_indicators,
    get_indicator_config,
    validate_indicator_thesis,
    get_indicator_display
)

# Timing constants (in minutes)
FIRST_REVALIDATION_MINUTES = 90   # First indicator recheck at 90 min
REVALIDATION_INTERVAL_MINUTES = 30  # Subsequent rechecks every 30 min  
HARD_TIMEOUT_MINUTES = 180        # 3-hour hard timeout

# Guidance zone thresholds (percentage toward TP)
PROGRESS_ZONE_THRESHOLD = 30      # 30% toward TP - progress update
BREAKEVEN_ZONE_THRESHOLD = 60     # 60% toward TP - breakeven advisory
DECISION_ZONE_THRESHOLD = 85      # 85% toward TP - final push update
GUIDANCE_COOLDOWN_MINUTES = 10    # Minimum time between guidance messages

class ForexSignalEngine:
    def __init__(self):
        self.symbol = 'XAU/USD'
        # Load config from database
        self.load_config()
        
        # Stagnant trade re-validation settings (from constants)
        self.revalidation_first_check_minutes = FIRST_REVALIDATION_MINUTES
        self.revalidation_interval_minutes = REVALIDATION_INTERVAL_MINUTES
        self.hard_timeout_minutes = HARD_TIMEOUT_MINUTES
    
    def load_config(self):
        """Load configuration from database or use defaults"""
        try:
            config = get_forex_config()
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40)
                self.rsi_overbought = config.get('rsi_overbought', 60)
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0)
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0)
                self.adx_threshold = config.get('adx_threshold', 15)
                self.trading_start_hour = config.get('trading_start_hour', 8)
                self.trading_end_hour = config.get('trading_end_hour', 22)
                print(f"[FOREX CONFIG] Loaded from database - RSI: {self.rsi_oversold}/{self.rsi_overbought}, ADX: {self.adx_threshold}, SL/TP: {self.atr_sl_multiplier}x/{self.atr_tp_multiplier}x")
            else:
                # Fallback to defaults
                self.rsi_oversold = 40
                self.rsi_overbought = 60
                self.atr_sl_multiplier = 2.0
                self.atr_tp_multiplier = 4.0
                self.adx_threshold = 15
                self.trading_start_hour = 8
                self.trading_end_hour = 22
                print("[FOREX CONFIG] Using default configuration")
        except Exception as e:
            # Fallback to defaults on error
            self.rsi_oversold = 40
            self.rsi_overbought = 60
            self.atr_sl_multiplier = 2.0
            self.atr_tp_multiplier = 4.0
            self.adx_threshold = 15
            self.trading_start_hour = 8
            self.trading_end_hour = 22
            print(f"[FOREX CONFIG] Error loading config, using defaults: {e}")
    
    def reload_config(self):
        """Reload configuration from database"""
        print("[FOREX CONFIG] Reloading configuration...")
        self.load_config()
        
    def calculate_tp_sl(self, entry_price, atr_value, signal_type):
        """
        Calculate Take Profit and Stop Loss using ATR-based method
        
        Args:
            entry_price: Entry price for the signal
            atr_value: Current ATR value
            signal_type: 'BUY' or 'SELL'
        
        Returns:
            tuple: (take_profit, stop_loss)
        """
        if signal_type == 'BUY':
            stop_loss = round(entry_price - (atr_value * self.atr_sl_multiplier), 2)
            take_profit = round(entry_price + (atr_value * self.atr_tp_multiplier), 2)
        else:
            stop_loss = round(entry_price + (atr_value * self.atr_sl_multiplier), 2)
            take_profit = round(entry_price - (atr_value * self.atr_tp_multiplier), 2)
        
        return take_profit, stop_loss
    
    async def check_for_signals(self, timeframe='15min'):
        """
        Check market conditions using multi-indicator strategy
        
        Strategy:
        1. Trend bias: 1-hour EMA 50/200 crossover
        2. Trend strength: ADX > 20
        3. Entry conditions: RSI 40/60 + MACD histogram direction
        4. Confirmation: Bollinger Bands touch + Stochastic extreme
        
        Returns:
            dict: Signal data or None if no signal
        """
        try:
            print(f"\n[FOREX SIGNALS] Checking for signals on {self.symbol} {timeframe}...")
            
            # Fetch all indicators (no rate limiting needed with unlimited API plan)
            price = twelve_data_client.get_price(self.symbol)
            rsi = twelve_data_client.get_rsi(self.symbol, timeframe)
            macd_data = twelve_data_client.get_macd(self.symbol, timeframe)
            atr = twelve_data_client.get_atr(self.symbol, timeframe)
            adx = twelve_data_client.get_adx(self.symbol, timeframe)
            bbands = twelve_data_client.get_bbands(self.symbol, timeframe)
            stoch = twelve_data_client.get_stoch(self.symbol, timeframe)
            ema50 = twelve_data_client.get_ema(self.symbol, '1h', 50)
            ema200 = twelve_data_client.get_ema(self.symbol, '1h', 200)
            
            # Check if we have all required data
            if not all([price, rsi, macd_data, atr, adx, bbands, stoch, ema50, ema200]):
                print("[FOREX SIGNALS] ❌ Missing indicator data, skipping signal check")
                return None
            
            # Type assertions for type checker (we know these are not None after the check above)
            assert price is not None
            assert rsi is not None
            assert macd_data is not None
            assert atr is not None
            assert adx is not None
            assert bbands is not None
            assert stoch is not None
            assert ema50 is not None
            assert ema200 is not None
            
            print(f"[FOREX SIGNALS] Price: {price:.2f}, RSI: {rsi:.2f}, MACD: {macd_data['macd']:.4f}, ADX: {adx:.2f}")
            print(f"[FOREX SIGNALS] Trend: EMA50={ema50:.2f}, EMA200={ema200:.2f}, Stoch K={stoch['k']:.2f}")
            
            # Step 1: Determine trend bias from 1-hour EMAs (for info only in testing mode)
            trend_is_bullish = ema50 > ema200
            trend_is_bearish = ema50 < ema200
            trend_name = "Bullish" if trend_is_bullish else "Bearish" if trend_is_bearish else "Neutral"
            
            # Step 2: Check trend strength with ADX
            if adx < self.adx_threshold:
                print(f"[FOREX SIGNALS] Weak trend - ADX {adx:.2f} < {self.adx_threshold}")
                return None
            
            # Step 3: Check MACD histogram slope (for info only in testing mode)
            macd_histogram = macd_data['histogram']
            macd_slope = macd_data['histogram_slope']
            
            print(f"[FOREX SIGNALS] MACD Histogram: {macd_histogram:.4f}, Slope: {macd_slope:.4f}")
            
            # Step 4: Check for signal conditions - TESTING MODE (RSI-based only)
            signal_type = None
            
            # BUY signal: RSI oversold + at least 1 confirmation (ignore trend/MACD for testing)
            if rsi < self.rsi_oversold:
                # Check Bollinger Bands (price near lower band = oversold)
                bb_distance = abs(price - bbands['lower'])
                bb_touch = bb_distance < (atr * 0.5)
                
                # Check Stochastic (oversold)
                stoch_oversold = stoch['is_oversold']
                
                # Require at least 1 confirmation (BB touch OR Stochastic)
                if bb_touch or stoch_oversold:
                    confirmations = []
                    if bb_touch:
                        confirmations.append("BB_touch")
                    if stoch_oversold:
                        confirmations.append("Stoch_oversold")
                    
                    signal_type = 'BUY'
                    print(f"[FOREX SIGNALS] 🟢 BUY signal - Trend={trend_name}, RSI={rsi:.2f}, ADX={adx:.2f}, Confirmations={confirmations}")
                else:
                    print(f"[FOREX SIGNALS] BUY conditions partial - BB_touch={bb_touch}, Stoch_oversold={stoch_oversold}")
            
            # SELL signal: RSI overbought + at least 1 confirmation (ignore trend/MACD for testing)
            elif rsi > self.rsi_overbought:
                # Check Bollinger Bands (price near upper band = overbought)
                bb_distance = abs(price - bbands['upper'])
                bb_touch = bb_distance < (atr * 0.5)
                
                # Check Stochastic (overbought)
                stoch_overbought = stoch['is_overbought']
                
                # Require at least 1 confirmation (BB touch OR Stochastic)
                if bb_touch or stoch_overbought:
                    confirmations = []
                    if bb_touch:
                        confirmations.append("BB_touch")
                    if stoch_overbought:
                        confirmations.append("Stoch_overbought")
                    
                    signal_type = 'SELL'
                    print(f"[FOREX SIGNALS] 🔴 SELL signal - Trend=Bearish, RSI={rsi:.2f}, ADX={adx:.2f}, Confirmations={confirmations}")
                else:
                    print(f"[FOREX SIGNALS] SELL conditions partial - BB_touch={bb_touch}, Stoch_overbought={stoch_overbought}")
            
            if not signal_type:
                macd_momentum = 'Increasing_Bullish' if macd_slope > 0 and macd_histogram > 0 else 'Increasing_Bearish' if macd_slope < 0 and macd_histogram < 0 else 'Not_Increasing'
                print(f"[FOREX SIGNALS] No signal - Trend={'Bullish' if trend_is_bullish else 'Bearish'}, RSI={rsi:.2f}, MACD_momentum={macd_momentum}")
                return None
            
            # Calculate TP/SL
            take_profit, stop_loss = self.calculate_tp_sl(price, atr, signal_type)
            
            # Build dynamic indicators dict from all fetched indicators
            all_indicators = {
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
            
            signal_data = {
                'signal_type': signal_type,
                'pair': self.symbol,
                'timeframe': timeframe,
                'entry_price': price,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'rsi_value': rsi,
                'macd_value': macd_data['macd'],
                'atr_value': atr,
                'adx_value': adx,
                'stoch_k_value': stoch['k'],
                'all_indicators': all_indicators
            }
            
            print(f"[FOREX SIGNALS] ✅ Signal generated: {signal_type} @ {price:.2f}, TP: {take_profit:.2f}, SL: {stop_loss:.2f}")
            
            return signal_data
            
        except Exception as e:
            print(f"[FOREX SIGNALS] ❌ Error checking for signals: {e}")
            return None
    
    async def monitor_active_signals(self):
        """
        Monitor active signals for TP/SL hits and expiration
        Returns list of signals that need updates
        """
        try:
            active_signals = get_forex_signals(status='pending')
            
            if not active_signals:
                return []
            
            print(f"\n[FOREX MONITOR] Checking {len(active_signals)} active signals...")
            
            current_price = twelve_data_client.get_price(self.symbol)
            if not current_price:
                print("[FOREX MONITOR] ❌ Could not fetch current price")
                return []
            
            print(f"[FOREX MONITOR] Current {self.symbol} price: {current_price:.2f}")
            
            updates = []
            now = datetime.utcnow()
            
            for signal in active_signals:
                signal_id = signal['id']
                signal_type = signal['signal_type']
                entry = float(signal['entry_price'])
                tp = float(signal['take_profit'])
                sl = float(signal['stop_loss'])
                posted_at = signal['posted_at']
                
                # Parse posted_at if it's a string
                if isinstance(posted_at, str):
                    posted_at = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
                
                hours_elapsed = (now - posted_at).total_seconds() / 3600
                
                if hours_elapsed >= 4:
                    print(f"[FOREX MONITOR] ⏱️  Signal #{signal_id} expired after 4 hours")
                    updates.append({
                        'id': signal_id,
                        'status': 'expired',
                        'pips': 0
                    })
                    continue
                
                if signal_type == 'BUY':
                    if current_price >= tp:
                        pips = round(tp - entry, 2)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP HIT! Profit: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'won',
                            'pips': pips
                        })
                    elif current_price <= sl:
                        pips = round(entry - sl, 2)
                        print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL HIT! Loss: -{pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'lost',
                            'pips': -pips
                        })
                else:
                    if current_price <= tp:
                        pips = round(entry - tp, 2)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP HIT! Profit: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'won',
                            'pips': pips
                        })
                    elif current_price >= sl:
                        pips = round(sl - entry, 2)
                        print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL HIT! Loss: -{pips} pips")
                        updates.append({
                            'id': signal_id,
                            'status': 'lost',
                            'pips': -pips
                        })
            
            return updates
            
        except Exception as e:
            print(f"[FOREX MONITOR] ❌ Error monitoring signals: {e}")
            return []
    
    def is_trading_hours(self):
        """
        Check if current time is within trading hours (configurable, default 8AM-10PM GMT)
        """
        from datetime import datetime
        now = datetime.utcnow()
        current_hour = now.hour
        
        if self.trading_start_hour <= current_hour < self.trading_end_hour:
            return True
        return False
    
    async def check_signal_guidance(self):
        """
        Check active signals for progress-based guidance updates.
        Returns list of guidance events to post.
        
        Progress zones (toward TP):
        - 30%: First progress update
        - 60%: Breakeven advisory  
        - 85%: Strong momentum update
        
        Caution zones (toward SL):
        - 30%: Early warning
        - 60%: Decision point (consider early exit)
        """
        try:
            active_signals = get_forex_signals(status='pending')
            
            if not active_signals:
                return []
            
            current_price = twelve_data_client.get_price(self.symbol)
            if not current_price:
                return []
            
            guidance_events = []
            now = datetime.utcnow()
            
            for signal in active_signals:
                signal_id = signal['id']
                signal_type = signal['signal_type']
                entry = float(signal['entry_price'])
                tp = float(signal['take_profit'])
                sl = float(signal['stop_loss'])
                breakeven_set = signal.get('breakeven_set', False)
                last_guidance_at = signal.get('last_guidance_at')
                last_progress_zone = signal.get('last_progress_zone', 0)
                last_caution_zone = signal.get('last_caution_zone', 0)
                
                if last_guidance_at:
                    if isinstance(last_guidance_at, str):
                        last_guidance_at = datetime.fromisoformat(last_guidance_at.replace('Z', '+00:00'))
                    minutes_since_guidance = (now - last_guidance_at).total_seconds() / 60
                    if minutes_since_guidance < GUIDANCE_COOLDOWN_MINUTES:
                        continue
                
                if signal_type == 'BUY':
                    tp_distance = tp - entry
                    sl_distance = entry - sl
                    
                    if tp_distance <= 0 or sl_distance <= 0:
                        print(f"[GUIDANCE] ⚠️ Signal #{signal_id}: Invalid distances (TP:{tp_distance}, SL:{sl_distance}), skipping")
                        continue
                    
                    if current_price >= entry:
                        progress = ((current_price - entry) / tp_distance) * 100
                        progress_toward = 'tp'
                    else:
                        progress = ((entry - current_price) / sl_distance) * 100
                        progress_toward = 'sl'
                else:
                    tp_distance = entry - tp
                    sl_distance = sl - entry
                    
                    if tp_distance <= 0 or sl_distance <= 0:
                        print(f"[GUIDANCE] ⚠️ Signal #{signal_id}: Invalid distances (TP:{tp_distance}, SL:{sl_distance}), skipping")
                        continue
                    
                    if current_price <= entry:
                        progress = ((entry - current_price) / tp_distance) * 100
                        progress_toward = 'tp'
                    else:
                        progress = ((current_price - entry) / sl_distance) * 100
                        progress_toward = 'sl'
                
                print(f"[GUIDANCE] Signal #{signal_id}: {signal_type} @ {entry:.2f}, price={current_price:.2f}, {progress:.1f}% toward {progress_toward.upper()}")
                
                progress = min(progress, 100)
                
                guidance_type = None
                zone_value = None
                
                if progress_toward == 'tp':
                    if progress >= BREAKEVEN_ZONE_THRESHOLD and not breakeven_set:
                        guidance_type = 'breakeven'
                        zone_value = BREAKEVEN_ZONE_THRESHOLD
                    elif progress >= DECISION_ZONE_THRESHOLD and last_progress_zone < DECISION_ZONE_THRESHOLD:
                        guidance_type = 'progress'
                        zone_value = DECISION_ZONE_THRESHOLD
                    elif progress >= BREAKEVEN_ZONE_THRESHOLD and last_progress_zone < BREAKEVEN_ZONE_THRESHOLD:
                        guidance_type = 'progress'
                        zone_value = BREAKEVEN_ZONE_THRESHOLD
                    elif progress >= PROGRESS_ZONE_THRESHOLD and last_progress_zone < PROGRESS_ZONE_THRESHOLD:
                        guidance_type = 'progress'
                        zone_value = PROGRESS_ZONE_THRESHOLD
                else:
                    if progress >= BREAKEVEN_ZONE_THRESHOLD and last_caution_zone < BREAKEVEN_ZONE_THRESHOLD:
                        guidance_type = 'decision'
                        zone_value = BREAKEVEN_ZONE_THRESHOLD
                    elif progress >= PROGRESS_ZONE_THRESHOLD and last_caution_zone < PROGRESS_ZONE_THRESHOLD:
                        guidance_type = 'caution'
                        zone_value = PROGRESS_ZONE_THRESHOLD
                
                if guidance_type:
                    progress_percent = progress if progress_toward == 'tp' else -progress
                    
                    guidance_events.append({
                        'signal_id': signal_id,
                        'signal_type': signal_type,
                        'guidance_type': guidance_type,
                        'progress_percent': progress_percent,
                        'current_price': current_price,
                        'entry_price': entry,
                        'take_profit': tp,
                        'stop_loss': sl,
                        'breakeven_set': breakeven_set,
                        'progress_toward': progress_toward,
                        'zone_value': zone_value
                    })
                    
                    print(f"[GUIDANCE] Signal #{signal_id}: {guidance_type} event ({progress:.0f}% toward {progress_toward.upper()}, zone {zone_value})")
            
            return guidance_events
            
        except Exception as e:
            print(f"[GUIDANCE] ❌ Error checking signal guidance: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def validate_thesis(self, signal, current_indicators):
        """
        Compare current indicators against original to determine thesis status.
        
        Uses the centralized indicator_config for validation rules, making it easy
        to add/remove indicators by updating the config rather than this function.
        
        Args:
            signal (dict): Signal data including original indicator values
            current_indicators (dict): Current indicator values {'rsi': X, 'macd': Y, ...}
        
        Returns:
            dict: {
                'status': 'intact' | 'weakening' | 'broken',
                'reasons': list of strings explaining the status,
                'indicators_changed': dict of indicator changes
            }
        """
        signal_type = signal['signal_type']
        
        # Get original indicators - prefer JSON column, fall back to legacy columns
        original_indicators = signal.get('original_indicators_json') or {}
        if not original_indicators:
            # Build from legacy columns for backward compatibility
            if signal.get('original_rsi') or signal.get('rsi_value'):
                original_indicators['rsi'] = signal.get('original_rsi') or signal.get('rsi_value')
            if signal.get('original_macd') or signal.get('macd_value'):
                original_indicators['macd'] = signal.get('original_macd') or signal.get('macd_value')
            if signal.get('original_adx'):
                original_indicators['adx'] = signal.get('original_adx')
            if signal.get('original_stoch_k'):
                original_indicators['stochastic'] = signal.get('original_stoch_k')
        
        reasons = []
        indicators_changed = {}
        weakening_count = 0
        breaking_count = 0
        
        # Loop through all validation indicators from config
        for indicator_key in get_validation_indicators():
            original_val = original_indicators.get(indicator_key)
            current_val = current_indicators.get(indicator_key)
            
            # Skip if we don't have both values
            if original_val is None or current_val is None:
                continue
            
            # Record the change
            change = current_val - original_val
            indicators_changed[indicator_key] = {
                'original': original_val,
                'current': current_val,
                'change': change
            }
            
            # Use config-driven validation
            status, description = validate_indicator_thesis(
                indicator_key, current_val, original_val, signal_type
            )
            
            if status == 'broken':
                config = get_indicator_config(indicator_key)
                indicator_name = config['name'] if config else indicator_key
                reasons.append(f"{indicator_name}: {description or 'thesis broken'}")
                breaking_count += 1
            elif status == 'weakening':
                config = get_indicator_config(indicator_key)
                indicator_name = config['name'] if config else indicator_key
                reasons.append(f"{indicator_name}: {description or 'showing weakness'}")
                weakening_count += 1
        
        # Determine overall status
        if breaking_count >= 2:
            status = 'broken'
        elif breaking_count >= 1 or weakening_count >= 2:
            status = 'weakening'
        elif weakening_count >= 1:
            status = 'weakening'
        else:
            status = 'intact'
        
        return {
            'status': status,
            'reasons': reasons,
            'indicators_changed': indicators_changed,
            'weakening_count': weakening_count,
            'breaking_count': breaking_count
        }
    
    async def check_stagnant_signals(self):
        """
        Check for stagnant signals that need indicator re-validation or timeout.
        Returns list of events for signals that need updates.
        
        Timing:
        - First re-check at 90 minutes if still < 30% progress
        - Subsequent re-checks every 30 minutes
        - Hard timeout at 3 hours
        """
        try:
            active_signals = get_forex_signals(status='pending')
            
            if not active_signals:
                return []
            
            now = datetime.utcnow()
            revalidation_events = []
            
            for signal in active_signals:
                signal_id = signal['id']
                posted_at = signal.get('posted_at')
                last_progress_zone = signal.get('last_progress_zone', 0)
                last_caution_zone = signal.get('last_caution_zone', 0)
                last_revalidation_at = signal.get('last_revalidation_at')
                thesis_status = signal.get('thesis_status', 'intact')
                timeout_notified = signal.get('timeout_notified', False)
                
                # Parse timestamps
                if isinstance(posted_at, str):
                    posted_at = datetime.fromisoformat(posted_at.replace('Z', '+00:00').replace('+00:00', ''))
                if isinstance(last_revalidation_at, str):
                    last_revalidation_at = datetime.fromisoformat(last_revalidation_at.replace('Z', '+00:00').replace('+00:00', ''))
                
                if not posted_at:
                    continue
                
                minutes_elapsed = (now - posted_at).total_seconds() / 60
                
                # Check for hard timeout (3 hours = 180 minutes)
                if minutes_elapsed >= self.hard_timeout_minutes and not timeout_notified:
                    revalidation_events.append({
                        'signal_id': signal_id,
                        'event_type': 'timeout',
                        'signal': signal,
                        'minutes_elapsed': minutes_elapsed,
                        'reason': f"Trade has been open for {minutes_elapsed/60:.1f} hours without resolution"
                    })
                    print(f"[REVALIDATION] Signal #{signal_id}: Hard timeout after {minutes_elapsed:.0f} minutes")
                    continue
                
                # Only check stagnant trades (not yet hit progress threshold in either direction)
                if last_progress_zone >= PROGRESS_ZONE_THRESHOLD or last_caution_zone >= PROGRESS_ZONE_THRESHOLD:
                    continue
                
                # Check if first revalidation is due (90 minutes)
                if minutes_elapsed >= self.revalidation_first_check_minutes:
                    # Determine if we should do a revalidation
                    should_revalidate = False
                    
                    if last_revalidation_at is None:
                        # First revalidation
                        should_revalidate = True
                    else:
                        # Check if enough time has passed since last revalidation
                        minutes_since_last = (now - last_revalidation_at).total_seconds() / 60
                        if minutes_since_last >= self.revalidation_interval_minutes:
                            should_revalidate = True
                    
                    if should_revalidate:
                        revalidation_events.append({
                            'signal_id': signal_id,
                            'event_type': 'revalidation',
                            'signal': signal,
                            'minutes_elapsed': minutes_elapsed,
                            'current_thesis_status': thesis_status,
                            'reason': f"Stagnant trade at {minutes_elapsed:.0f} minutes, verifying thesis"
                        })
                        print(f"[REVALIDATION] Signal #{signal_id}: Scheduling revalidation at {minutes_elapsed:.0f} minutes")
            
            return revalidation_events
            
        except Exception as e:
            print(f"[REVALIDATION] ❌ Error checking stagnant signals: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def perform_revalidation(self, signal):
        """
        Perform indicator re-validation for a stagnant signal.
        
        Args:
            signal (dict): Signal data to revalidate
        
        Returns:
            dict: Validation result with status, reasons, and current indicators
        """
        try:
            signal_id = signal['id']
            timeframe = signal.get('timeframe', '15min')
            
            print(f"[REVALIDATION] Fetching current indicators for signal #{signal_id}...")
            
            # Fetch current indicator values (no rate limiting needed with unlimited API plan)
            rsi = twelve_data_client.get_rsi(self.symbol, timeframe)
            macd_data = twelve_data_client.get_macd(self.symbol, timeframe)
            adx = twelve_data_client.get_adx(self.symbol, timeframe)
            stoch = twelve_data_client.get_stoch(self.symbol, timeframe)
            
            if not all([rsi, macd_data, adx, stoch]):
                print(f"[REVALIDATION] ⚠️ Could not fetch all indicators for signal #{signal_id}")
                return None
            
            # Type assertions for type checker (we know these are not None after the check above)
            assert macd_data is not None
            assert stoch is not None
            
            current_indicators = {
                'rsi': rsi,
                'macd': macd_data['macd'],
                'adx': adx,
                'stochastic': stoch['k']
            }
            
            # Validate thesis
            validation = self.validate_thesis(signal, current_indicators)
            validation['current_indicators'] = current_indicators
            validation['signal_id'] = signal_id
            
            print(f"[REVALIDATION] Signal #{signal_id}: Thesis is {validation['status'].upper()}")
            if validation['reasons']:
                print(f"[REVALIDATION] Reasons: {', '.join(validation['reasons'])}")
            
            return validation
            
        except Exception as e:
            print(f"[REVALIDATION] ❌ Error performing revalidation: {e}")
            import traceback
            traceback.print_exc()
            return None

forex_signal_engine = ForexSignalEngine()
