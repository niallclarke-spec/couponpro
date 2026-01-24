"""
Price Monitoring Service
Monitors open signals, checks TP/SL hits, provides AI guidance,
and enforces 5-hour auto-close
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from forex_api import twelve_data_client
from core.pip_calculator import calculate_pips as calc_pips, PIPS_MULTIPLIER
from db import (
    get_open_signal, 
    update_forex_signal_status,
    update_signal_breakeven,
    update_signal_guidance
)


class PriceMonitor:
    """
    Monitors open signals for:
    - TP/SL hits every 5 minutes
    - AI guidance at 4 hours
    - Auto-close at 5 hours
    """
    
    def __init__(self):
        self.symbol = 'XAU/USD'
        self.breakeven_hour = 4
        self.max_hours = 5
        self.check_interval_minutes = 5
    
    def get_current_price(self) -> Optional[float]:
        """Get current market price"""
        try:
            return twelve_data_client.get_price(self.symbol)
        except Exception as e:
            print(f"[MONITOR] Error fetching price: {e}")
            return None
    
    def calculate_pips(self, signal_type: str, entry: float, current_or_target: float) -> float:
        """Calculate pips for XAU/USD trade (1 pip = $0.10, so $1 = 10 pips)"""
        if signal_type == 'BUY':
            dollar_diff = current_or_target - entry
        else:
            dollar_diff = entry - current_or_target
        # XAU/USD: 1 pip = $0.10, multiply by 10 to convert dollars to pips
        return round(dollar_diff * PIPS_MULTIPLIER, 1)
    
    async def check_signal_status(self) -> Optional[Dict[str, Any]]:
        """
        Check the status of the current open signal
        
        Returns:
            Dict with action to take (None if no action needed)
        """
        signal = get_open_signal()
        if not signal:
            return None
        
        current_price = self.get_current_price()
        if not current_price:
            print("[MONITOR] Could not fetch price, skipping check")
            return None
        
        signal_id = signal['id']
        signal_type = signal['signal_type']
        entry = float(signal['entry_price'])
        tp = float(signal['take_profit'])
        original_sl = float(signal['stop_loss'])
        effective_sl = signal.get('effective_sl')
        sl = float(effective_sl) if effective_sl else original_sl
        posted_at = signal['posted_at']
        breakeven_set = signal.get('breakeven_set', False)
        guidance_count = signal.get('guidance_count', 0)
        
        if isinstance(posted_at, str):
            posted_at = datetime.fromisoformat(posted_at.replace('Z', '+00:00').replace('+00:00', ''))
        
        now = datetime.utcnow()
        hours_elapsed = (now - posted_at).total_seconds() / 3600
        
        sl_note = f"(effective: ${sl:.2f})" if effective_sl else f"(original: ${sl:.2f})"
        print(f"[MONITOR] Signal #{signal_id}: {signal_type} @ {entry:.2f}, Current: {current_price:.2f}, SL {sl_note}, Hours: {hours_elapsed:.2f}")
        
        if self._check_tp_hit(signal_type, current_price, tp):
            pips = self.calculate_pips(signal_type, entry, tp)
            return {
                'action': 'tp_hit',
                'signal_id': signal_id,
                'signal_type': signal_type,
                'entry': entry,
                'exit_price': tp,
                'pips': pips,
                'status': 'won'
            }
        
        if self._check_sl_hit(signal_type, current_price, sl):
            pips = self.calculate_pips(signal_type, entry, sl)
            if pips >= 0:
                status = 'won'
                action = 'sl_hit_profit_locked'
            else:
                status = 'lost'
                action = 'sl_hit'
            return {
                'action': action,
                'signal_id': signal_id,
                'signal_type': signal_type,
                'entry': entry,
                'exit_price': sl,
                'pips': pips,
                'status': status
            }
        
        if hours_elapsed >= self.max_hours:
            pips = self.calculate_pips(signal_type, entry, current_price)
            status = 'won' if pips > 0 else 'lost'
            return {
                'action': 'timeout_close',
                'signal_id': signal_id,
                'signal_type': signal_type,
                'entry': entry,
                'exit_price': current_price,
                'pips': pips,
                'status': status,
                'reason': f'5-hour timeout reached. Closed at market price.'
            }
        
        if hours_elapsed >= self.breakeven_hour and not breakeven_set:
            current_pips = self.calculate_pips(signal_type, entry, current_price)
            return {
                'action': 'breakeven_guidance',
                'signal_id': signal_id,
                'signal_type': signal_type,
                'entry': entry,
                'current_price': current_price,
                'current_pips': current_pips,
                'hours_elapsed': hours_elapsed,
                'old_sl': sl,
                'old_tp': tp
            }
        
        if hours_elapsed >= 2 and guidance_count == 0:
            current_pips = self.calculate_pips(signal_type, entry, current_price)
            return {
                'action': 'mid_trade_update',
                'signal_id': signal_id,
                'signal_type': signal_type,
                'entry': entry,
                'current_price': current_price,
                'current_pips': current_pips,
                'hours_elapsed': hours_elapsed
            }
        
        return None
    
    def _check_tp_hit(self, signal_type: str, current_price: float, tp: float) -> bool:
        """Check if Take Profit was hit"""
        if signal_type == 'BUY':
            return current_price >= tp
        else:
            return current_price <= tp
    
    def _check_sl_hit(self, signal_type: str, current_price: float, sl: float) -> bool:
        """Check if Stop Loss was hit"""
        if signal_type == 'BUY':
            return current_price <= sl
        else:
            return current_price >= sl
    
    def apply_breakeven(self, signal_id: int, entry_price: float) -> bool:
        """Move stop loss to entry price (breakeven)"""
        try:
            update_signal_breakeven(signal_id, entry_price)
            print(f"[MONITOR] Signal #{signal_id} - SL moved to breakeven: {entry_price:.2f}")
            return True
        except Exception as e:
            print(f"[MONITOR] Error applying breakeven: {e}")
            return False
    
    def close_signal(self, signal_id: int, status: str, pips: float, close_price: float = None, tenant_id: str = 'entrylab') -> bool:
        """Close a signal with final status"""
        try:
            update_forex_signal_status(signal_id, status, tenant_id, result_pips=pips, close_price=close_price)
            print(f"[MONITOR] Signal #{signal_id} closed as {status} with {pips:+.2f} pips at ${close_price:.2f}" if close_price else f"[MONITOR] Signal #{signal_id} closed as {status} with {pips:+.2f} pips")
            return True
        except Exception as e:
            print(f"[MONITOR] Error closing signal: {e}")
            return False
    
    def add_guidance_note(self, signal_id: int, note: str) -> bool:
        """Add guidance note to signal"""
        try:
            update_signal_guidance(signal_id, note)
            print(f"[MONITOR] Guidance added to signal #{signal_id}")
            return True
        except Exception as e:
            print(f"[MONITOR] Error adding guidance: {e}")
            return False


price_monitor = PriceMonitor()
