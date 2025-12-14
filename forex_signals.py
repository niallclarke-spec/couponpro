"""
Forex signal generation engine
Modular strategy system with shared monitoring and guidance logic
"""
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from forex_api import twelve_data_client
from db import (
    create_forex_signal, get_forex_signals, update_forex_signal_status, get_forex_config,
    get_daily_pnl, get_last_completed_signal, add_signal_narrative, get_bot_config,
    update_tp_hit, update_breakeven_triggered, get_active_bot
)
from indicator_config import (
    get_validation_indicators,
    get_indicator_config,
    validate_indicator_thesis,
    get_indicator_display
)
from strategies import get_active_strategy, get_available_strategies, STRATEGY_REGISTRY
from strategies.base_strategy import SignalData

# Timing constants (in minutes)
FIRST_REVALIDATION_MINUTES = 90   # First indicator recheck at 90 min
REVALIDATION_INTERVAL_MINUTES = 30  # Subsequent rechecks every 30 min  
HARD_TIMEOUT_MINUTES = 180        # 3-hour hard timeout

# Guidance zone thresholds (percentage toward TP)
PROGRESS_ZONE_THRESHOLD = 30      # 30% toward TP - progress update
BREAKEVEN_ZONE_THRESHOLD = 70     # 70% toward TP - breakeven advisory (updated from 60)
DECISION_ZONE_THRESHOLD = 85      # 85% toward TP - final push update
GUIDANCE_COOLDOWN_MINUTES = 10    # Minimum time between guidance messages

class ForexSignalEngine:
    def __init__(self, tenant_id=None):
        self.symbol = 'XAU/USD'
        self.tenant_id = tenant_id or os.environ.get('TENANT_ID', 'entrylab')
        self._active_strategy = None
        self._active_bot_type = 'aggressive'
        
        # Load config from database
        self.load_config()
        self.load_active_strategy()
        
        # Stagnant trade re-validation settings (from constants)
        self.revalidation_first_check_minutes = FIRST_REVALIDATION_MINUTES
        self.revalidation_interval_minutes = REVALIDATION_INTERVAL_MINUTES
        self.hard_timeout_minutes = HARD_TIMEOUT_MINUTES
    
    def set_tenant_id(self, tenant_id):
        """Set tenant_id and reload config"""
        self.tenant_id = tenant_id
        self.load_config()
        self.load_active_strategy()
    
    def load_active_strategy(self):
        """Load the active strategy from bot_config table"""
        try:
            # Use get_active_bot() which reads from bot_config table (set by admin UI)
            self._active_bot_type = get_active_bot(tenant_id=self.tenant_id) or 'aggressive'
            
            self._active_strategy = get_active_strategy(self._active_bot_type)
            if self._active_strategy:
                print(f"[FOREX ENGINE] Loaded strategy: {self._active_strategy.name} ({self._active_bot_type})")
            else:
                print(f"[FOREX ENGINE] WARNING: Could not load strategy '{self._active_bot_type}', using aggressive")
                self._active_bot_type = 'aggressive'
                self._active_strategy = get_active_strategy('aggressive')
        except Exception as e:
            print(f"[FOREX ENGINE] Error loading strategy: {e}")
            self._active_bot_type = 'aggressive'
            self._active_strategy = get_active_strategy('aggressive')
    
    def get_active_strategy(self):
        """Get the currently active strategy instance"""
        if not self._active_strategy:
            self.load_active_strategy()
        return self._active_strategy
    
    def switch_strategy(self, bot_type: str) -> bool:
        """Switch to a different strategy"""
        if bot_type not in STRATEGY_REGISTRY:
            print(f"[FOREX ENGINE] Unknown strategy: {bot_type}")
            return False
        
        pending_signals = get_forex_signals(tenant_id=self.tenant_id, status='pending')
        if pending_signals and len(pending_signals) > 0:
            print(f"[FOREX ENGINE] Cannot switch strategy while signal #{pending_signals[0]['id']} is active")
            return False
        
        self._active_bot_type = bot_type
        self._active_strategy = get_active_strategy(bot_type)
        print(f"[FOREX ENGINE] Switched to strategy: {self._active_strategy.name}")
        return True
    
    def get_available_strategies(self):
        """Get list of available strategies"""
        return get_available_strategies()
    
    def load_config(self):
        """Load configuration from database or use defaults"""
        try:
            config = get_forex_config(tenant_id=self.tenant_id)
            if config:
                self.rsi_oversold = config.get('rsi_oversold', 40)
                self.rsi_overbought = config.get('rsi_overbought', 60)
                self.atr_sl_multiplier = config.get('atr_sl_multiplier', 2.0)
                self.atr_tp_multiplier = config.get('atr_tp_multiplier', 4.0)
                self.adx_threshold = config.get('adx_threshold', 15)
                self.trading_start_hour = config.get('trading_start_hour', 8)
                self.trading_end_hour = config.get('trading_end_hour', 22)
                # Guardrail settings (convert from string to proper types)
                self.daily_loss_cap_pips = float(config.get('daily_loss_cap_pips', 50.0))
                self.back_to_back_throttle_minutes = int(config.get('back_to_back_throttle_minutes', 30))
                session_filter = config.get('session_filter_enabled', 'true')
                # Normalize case-insensitive: 'true', 'True', 'TRUE' all work
                self.session_filter_enabled = str(session_filter).lower() == 'true' if isinstance(session_filter, str) else bool(session_filter)
                self.session_start_hour_utc = int(config.get('session_start_hour_utc', 8))
                self.session_end_hour_utc = int(config.get('session_end_hour_utc', 21))
                print(f"[FOREX CONFIG] Loaded from database - RSI: {self.rsi_oversold}/{self.rsi_overbought}, ADX: {self.adx_threshold}, SL/TP: {self.atr_sl_multiplier}x/{self.atr_tp_multiplier}x")
                print(f"[FOREX CONFIG] Guardrails - Loss cap: {self.daily_loss_cap_pips} pips, Throttle: {self.back_to_back_throttle_minutes}min, Session: {self.session_start_hour_utc}-{self.session_end_hour_utc} UTC (enabled={self.session_filter_enabled})")
            else:
                # Fallback to defaults
                self.rsi_oversold = 40
                self.rsi_overbought = 60
                self.atr_sl_multiplier = 2.0
                self.atr_tp_multiplier = 4.0
                self.adx_threshold = 15
                self.trading_start_hour = 8
                self.trading_end_hour = 22
                self.daily_loss_cap_pips = 50.0
                self.back_to_back_throttle_minutes = 30
                self.session_filter_enabled = True
                self.session_start_hour_utc = 8
                self.session_end_hour_utc = 21
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
            self.daily_loss_cap_pips = 50.0
            self.back_to_back_throttle_minutes = 30
            self.session_filter_enabled = True
            self.session_start_hour_utc = 8
            self.session_end_hour_utc = 21
            print(f"[FOREX CONFIG] Error loading config, using defaults: {e}")
    
    def reload_config(self):
        """Reload configuration and active strategy from database (hot-reload)"""
        print("[FOREX CONFIG] Reloading configuration...")
        self.load_config()
        
        new_bot_type = get_active_bot(tenant_id=self.tenant_id) or 'aggressive'
        if new_bot_type != self._active_bot_type:
            print(f"[FOREX CONFIG] Strategy changed: {self._active_bot_type} -> {new_bot_type}")
            self._active_bot_type = new_bot_type
            self._active_strategy = get_active_strategy(new_bot_type)
            if self._active_strategy:
                print(f"[FOREX CONFIG] Hot-reloaded strategy: {self._active_strategy.name}")
            else:
                print(f"[FOREX CONFIG] WARNING: Could not load strategy '{new_bot_type}'")
        else:
            print(f"[FOREX CONFIG] Strategy unchanged: {self._active_bot_type}")
    
    def check_guardrails(self):
        """
        Check all guardrails before generating a new signal.
        
        Returns:
            tuple: (can_generate: bool, reason: str or None)
        """
        now = datetime.utcnow()
        
        # 1. Check session window (3 AM - 4 PM EST = 8 AM - 9 PM UTC)
        if self.session_filter_enabled:
            current_hour = now.hour
            if not (self.session_start_hour_utc <= current_hour < self.session_end_hour_utc):
                return False, f"Outside trading session ({self.session_start_hour_utc}:00-{self.session_end_hour_utc}:00 UTC)"
        
        # 2. Check daily loss cap (use <= to pause AT the threshold, not just past it)
        daily_pnl = get_daily_pnl()
        if daily_pnl <= -self.daily_loss_cap_pips:
            return False, f"Daily loss cap reached ({daily_pnl:.1f} pips, cap: -{self.daily_loss_cap_pips})"
        
        # 3. Check back-to-back loss throttle
        last_signal = get_last_completed_signal()
        if last_signal and last_signal['status'] == 'lost':
            closed_at = last_signal['closed_at']
            if closed_at:
                # Handle both datetime and string
                if isinstance(closed_at, str):
                    closed_at = datetime.fromisoformat(closed_at.replace('Z', '+00:00').replace('+00:00', ''))
                minutes_since_loss = (now - closed_at).total_seconds() / 60
                if minutes_since_loss < self.back_to_back_throttle_minutes:
                    remaining = int(self.back_to_back_throttle_minutes - minutes_since_loss)
                    return False, f"Loss throttle active ({remaining}min remaining after previous loss)"
        
        return True, None
        
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
    
    async def check_for_signals(self, timeframe='15min') -> Optional[Dict[str, Any]]:
        """
        Check market conditions using the active strategy.
        Delegates to the modular strategy system.
        
        Returns:
            dict: Signal data or None if no signal
        """
        try:
            strategy = self.get_active_strategy()
            if not strategy:
                print("[FOREX SIGNALS] ❌ No active strategy loaded")
                return None
            
            print(f"\n[FOREX SIGNALS] Using strategy: {strategy.name} ({strategy.bot_type})")
            
            signal_data = await strategy.check_for_signals(timeframe)
            
            if not signal_data:
                return None
            
            result = signal_data.to_dict()
            
            result['rsi_value'] = signal_data.indicators.get('rsi')
            result['macd_value'] = signal_data.indicators.get('macd')
            result['atr_value'] = signal_data.indicators.get('atr')
            result['adx_value'] = signal_data.indicators.get('adx')
            result['stoch_k_value'] = signal_data.indicators.get('stochastic')
            
            print(f"[FOREX SIGNALS] ✅ Signal from {strategy.name}: {signal_data.signal_type} @ {signal_data.entry_price:.2f}")
            
            return result
            
        except Exception as e:
            print(f"[FOREX SIGNALS] ❌ Error checking for signals: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def monitor_active_signals(self):
        """
        Monitor active signals for multi-TP hits, SL hits, breakeven trigger, and expiration.
        
        Multi-TP System:
        - TP1: 50% position close
        - TP2: 30% position close  
        - TP3: 20% position close (full exit)
        - Breakeven alert at 70% toward TP1
        
        Returns list of events that need updates/notifications
        """
        try:
            active_signals = get_forex_signals(tenant_id=self.tenant_id, status='pending')
            
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
                tp1 = float(signal['take_profit'])
                tp2 = float(signal.get('take_profit_2') or 0)
                tp3 = float(signal.get('take_profit_3') or 0)
                original_sl = float(signal['stop_loss'])
                effective_sl = signal.get('effective_sl')
                sl = float(effective_sl) if effective_sl else original_sl
                posted_at = signal['posted_at']
                
                tp1_hit = signal.get('tp1_hit', False) or signal.get('tp_hit_1', False)
                tp2_hit = signal.get('tp2_hit', False) or signal.get('tp_hit_2', False)
                tp3_hit = signal.get('tp3_hit', False) or signal.get('tp_hit_3', False)
                breakeven_triggered = signal.get('breakeven_triggered', False)
                
                tp1_pct = signal.get('tp1_percentage') or 50
                tp2_pct = signal.get('tp2_percentage') or 30
                tp3_pct = signal.get('tp3_percentage') or 20
                
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
                
                is_buy = signal_type == 'BUY'
                has_tp2 = tp2 > 0
                has_tp3 = tp3 > 0
                tp_count = 1 + (1 if has_tp2 else 0) + (1 if has_tp3 else 0)
                
                if is_buy:
                    # XAU/USD: 1 pip = $0.01, multiply by 100
                    if not tp1_hit and current_price >= tp1:
                        pips = round((tp1 - entry) * 100, 1)
                        remaining = (tp2_pct if has_tp2 else 0) + (tp3_pct if has_tp3 else 0)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP1 HIT! +{pips} pips ({tp1_pct}% closed)")
                        update_tp_hit(signal_id, 1)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp1_hit',
                            'pips': pips,
                            'percentage': tp1_pct,
                            'remaining': remaining
                        })
                        if tp_count == 1:
                            updates.append({
                                'id': signal_id,
                                'status': 'won',
                                'pips': pips
                            })
                            continue
                    
                    if has_tp2 and tp1_hit and not tp2_hit and current_price >= tp2:
                        pips = round((tp2 - entry) * 100, 1)
                        remaining = tp3_pct if has_tp3 else 0
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP2 HIT! +{pips} pips ({tp2_pct}% closed)")
                        update_tp_hit(signal_id, 2)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp2_hit',
                            'pips': pips,
                            'percentage': tp2_pct,
                            'remaining': remaining
                        })
                        if tp_count == 2:
                            updates.append({
                                'id': signal_id,
                                'status': 'won',
                                'pips': pips
                            })
                            continue
                    
                    if has_tp3 and tp2_hit and not tp3_hit and current_price >= tp3:
                        pips = round((tp3 - entry) * 100, 1)
                        print(f"[FOREX MONITOR] 🎯 Signal #{signal_id} TP3 HIT! +{pips} pips - FULL EXIT")
                        update_tp_hit(signal_id, 3)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp3_hit',
                            'status': 'won',
                            'pips': pips,
                            'percentage': tp3_pct
                        })
                        continue
                    
                    if current_price <= sl:
                        pips = round((sl - entry) * 100, 1)
                        sl_type = "effective" if effective_sl else "original"
                        if pips > 0:
                            status = 'won'
                            event = 'sl_hit_profit_locked'
                            print(f"[FOREX MONITOR] ✅ Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Locked profit: +{pips} pips")
                        elif pips == 0:
                            status = 'won'
                            event = 'sl_hit_breakeven'
                            print(f"[FOREX MONITOR] 🔒 Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Breakeven exit")
                        else:
                            status = 'lost'
                            event = 'sl_hit'
                            print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Loss: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'event': event,
                            'status': status,
                            'pips': pips,
                            'exit_price': current_price
                        })
                    
                else:
                    # XAU/USD: 1 pip = $0.01, multiply by 100
                    if not tp1_hit and current_price <= tp1:
                        pips = round((entry - tp1) * 100, 1)
                        remaining = (tp2_pct if has_tp2 else 0) + (tp3_pct if has_tp3 else 0)
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP1 HIT! +{pips} pips ({tp1_pct}% closed)")
                        update_tp_hit(signal_id, 1)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp1_hit',
                            'pips': pips,
                            'percentage': tp1_pct,
                            'remaining': remaining
                        })
                        if tp_count == 1:
                            updates.append({
                                'id': signal_id,
                                'status': 'won',
                                'pips': pips
                            })
                            continue
                    
                    if has_tp2 and tp1_hit and not tp2_hit and current_price <= tp2:
                        pips = round((entry - tp2) * 100, 1)
                        remaining = tp3_pct if has_tp3 else 0
                        print(f"[FOREX MONITOR] ✅ Signal #{signal_id} TP2 HIT! +{pips} pips ({tp2_pct}% closed)")
                        update_tp_hit(signal_id, 2)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp2_hit',
                            'pips': pips,
                            'percentage': tp2_pct,
                            'remaining': remaining
                        })
                        if tp_count == 2:
                            updates.append({
                                'id': signal_id,
                                'status': 'won',
                                'pips': pips
                            })
                            continue
                    
                    if has_tp3 and tp2_hit and not tp3_hit and current_price <= tp3:
                        pips = round((entry - tp3) * 100, 1)
                        print(f"[FOREX MONITOR] 🎯 Signal #{signal_id} TP3 HIT! +{pips} pips - FULL EXIT")
                        update_tp_hit(signal_id, 3)
                        updates.append({
                            'id': signal_id,
                            'event': 'tp3_hit',
                            'status': 'won',
                            'pips': pips,
                            'percentage': tp3_pct
                        })
                        continue
                    
                    if current_price >= sl:
                        pips = round((entry - sl) * 100, 1)
                        sl_type = "effective" if effective_sl else "original"
                        if pips > 0:
                            status = 'won'
                            event = 'sl_hit_profit_locked'
                            print(f"[FOREX MONITOR] ✅ Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Locked profit: +{pips} pips")
                        elif pips == 0:
                            status = 'won'
                            event = 'sl_hit_breakeven'
                            print(f"[FOREX MONITOR] 🔒 Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Breakeven exit")
                        else:
                            status = 'lost'
                            event = 'sl_hit'
                            print(f"[FOREX MONITOR] ❌ Signal #{signal_id} SL ({sl_type}) HIT @ ${sl:.2f}! Loss: {pips} pips")
                        updates.append({
                            'id': signal_id,
                            'event': event,
                            'status': status,
                            'pips': pips,
                            'exit_price': current_price
                        })
            
            return updates
            
        except Exception as e:
            print(f"[FOREX MONITOR] ❌ Error monitoring signals: {e}")
            import traceback
            traceback.print_exc()
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
            active_signals = get_forex_signals(tenant_id=self.tenant_id, status='pending')
            
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
            active_signals = get_forex_signals(tenant_id=self.tenant_id, status='pending')
            
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
