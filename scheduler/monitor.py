"""
Scheduler Monitor Module

Responsible for monitoring active signals:
- TP1/TP2/TP3 hits
- SL hits (including profit-locked and breakeven)
- Breakeven alerts
- Signal expiration
- Milestone progress notifications
- Stagnant signal revalidation and timeout
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.logging import get_logger
from core.runtime import TenantRuntime
from scheduler.messenger import Messenger
from forex_ai import (
    generate_revalidation_message,
    generate_timeout_message
)

logger = get_logger(__name__)


class SignalMonitor:
    """
    Monitors active forex signals for TP/SL hits and milestones.
    
    Responsibilities:
    - Monitor active signals for price target hits
    - Send TP/SL notifications via messenger
    - Track and send milestone progress updates
    - Handle signal revalidation and timeout
    """
    
    def __init__(self, runtime: TenantRuntime, messenger: Messenger):
        self.runtime = runtime
        self.messenger = messenger
        self.tenant_id = runtime.tenant_id
    
    @property
    def signal_engine(self):
        """Get the signal engine from runtime."""
        return self.runtime.get_signal_engine()
    
    @property
    def price_client(self):
        """Get the price client from runtime."""
        return self.runtime.get_price_client()
    
    @property
    def milestone_tracker(self):
        """Get the milestone tracker from runtime."""
        return self.runtime.get_milestone_tracker()
    
    async def run_signal_monitoring(self) -> List[Dict[str, Any]]:
        """
        Monitor active signals for multi-TP hits, SL hits, and breakeven.
        
        Returns:
            List of signal update events that were processed
        """
        try:
            with self.runtime.request_context():
                updates = await self.signal_engine.monitor_active_signals()
                
                for update in updates:
                    await self._process_signal_update(update)
                
                return updates
                
        except Exception as e:
            logger.exception("❌ Error in signal monitoring")
            return []
    
    async def _process_signal_update(self, update: Dict[str, Any]):
        """Process a single signal update event."""
        signal_id = update['id']
        event = update.get('event')
        status = update.get('status')
        pips = update.get('pips', 0)
        close_price = update.get('exit_price') or update.get('current_price')
        
        signals_data = self.runtime.get_forex_signals(status=None, limit=10)
        matching_signal = next((s for s in signals_data if s['id'] == signal_id), None)
        signal_type = matching_signal.get('signal_type', 'BUY') if matching_signal else 'BUY'
        
        db = self.runtime.db
        
        if event == 'breakeven_alert':
            pass
        
        elif event == 'tp1_hit':
            remaining = update.get('remaining', 0)
            await self.messenger.send_tp1_celebration(signal_type, pips, remaining)
            if remaining > 0 and matching_signal:
                tp1_price = float(matching_signal.get('take_profit', 0))
                db.update_effective_sl(signal_id, tp1_price, tenant_id=self.tenant_id)
                logger.info(f"🔒 Set effective_sl to TP1 (${tp1_price:.2f}) for signal #{signal_id}")
        
        elif event == 'tp2_hit':
            remaining = update.get('remaining', 0)
            tp1_price = matching_signal.get('take_profit', 0) if matching_signal else 0
            tp2_price = matching_signal.get('take_profit_2', 0) if matching_signal else 0
            await self.messenger.send_tp2_celebration(signal_type, pips, float(tp1_price), remaining)
            if remaining > 0 and tp2_price:
                db.update_effective_sl(signal_id, float(tp2_price), tenant_id=self.tenant_id)
                logger.info(f"🔒 Set effective_sl to TP2 (${float(tp2_price):.2f}) for signal #{signal_id}")
        
        elif event == 'tp3_hit':
            await self.messenger.send_tp3_celebration(signal_type, pips)
            if status == 'won':
                self.runtime.update_forex_signal_status(signal_id, 'won', pips, close_price)
                logger.info(f"✅ Signal #{signal_id} completed - all TPs hit!")
        
        elif event == 'sl_hit_profit_locked':
            self.runtime.update_forex_signal_status(signal_id, 'won', pips, close_price)
            await self.messenger.send_profit_locked_message(pips)
        
        elif event == 'sl_hit_breakeven':
            self.runtime.update_forex_signal_status(signal_id, 'won', pips, close_price)
            await self.messenger.send_breakeven_exit_message()
        
        elif event == 'sl_hit':
            self.runtime.update_forex_signal_status(signal_id, status, pips, close_price)
            await self.messenger.send_sl_hit_message(pips)
        
        elif status == 'won':
            self.runtime.update_forex_signal_status(signal_id, status, pips, close_price)
            await self.messenger.send_tp1_celebration(signal_type, pips, 0)
            
        elif status == 'lost':
            self.runtime.update_forex_signal_status(signal_id, status, pips, close_price)
            await self.messenger.send_sl_hit_message(pips)
            
        elif status == 'expired':
            final_status = 'won' if pips > 0 else 'expired'
            self.runtime.update_forex_signal_status(signal_id, final_status, pips, close_price)
            await self.messenger.post_signal_expired(signal_id, pips, signal_type)
            logger.info(f"✅ Posted expiry notification for signal #{signal_id} (status: {final_status})")
        
        if status in ('won', 'lost', 'expired'):
            self.signal_engine.load_active_strategy()
            logger.info(f"Strategy reloaded after signal #{signal_id} closed")
    
    async def run_signal_guidance(self):
        """
        Check for milestone-based progress updates on active signals.
        
        Milestones:
        - 40% toward TP1: AI motivational message
        - 70% toward TP1: Breakeven alert
        - 50% toward TP2: Small celebration
        - 60% toward SL: Warning
        """
        try:
            with self.runtime.request_context():
                active_signals = self.runtime.get_forex_signals(status='pending')
                
                if not active_signals:
                    return
                
                current_price = self.price_client.get_price(self.signal_engine.symbol)
                if not current_price:
                    return
                
                db = self.runtime.db
                
                for signal in active_signals:
                    signal_id = signal['id']
                    
                    milestone_event = self.milestone_tracker.check_milestones(signal, current_price)
                    
                    if milestone_event:
                        milestone = milestone_event['milestone']
                        milestone_key = milestone_event['milestone_key']
                        
                        claimed = db.update_milestone_sent(signal_id, milestone_key, tenant_id=self.tenant_id)
                        
                        if not claimed:
                            logger.info(f"⏭️ Milestone {milestone_key} already claimed for signal #{signal_id}")
                            continue
                        
                        success = await self.messenger.send_milestone_message(milestone_event)
                        
                        if success and milestone == 'tp1_70_breakeven':
                            db.update_signal_breakeven(signal_id, milestone_event['entry_price'], tenant_id=self.tenant_id)
                            db.update_effective_sl(signal_id, milestone_event['entry_price'], tenant_id=self.tenant_id)
                            logger.info(f"🔒 Set effective_sl to entry (breakeven) for signal #{signal_id}")
                
        except Exception as e:
            logger.exception("❌ Error in signal guidance")
    
    async def run_stagnant_signal_checks(self):
        """Check stagnant signals for re-validation and timeout."""
        try:
            with self.runtime.request_context():
                revalidation_events = await self.signal_engine.check_stagnant_signals()
                
                db = self.runtime.db
                
                for event in revalidation_events:
                    signal_id = event['signal_id']
                    event_type = event['event_type']
                    signal = event['signal']
                    minutes_elapsed = event['minutes_elapsed']
                    
                    signal_type = signal['signal_type']
                    entry = float(signal['entry_price'])
                    tp = float(signal['take_profit'])
                    sl = float(signal['stop_loss'])
                    
                    current_price = self.price_client.get_price(self.signal_engine.symbol)
                    if not current_price:
                        logger.warning(f"⚠️ Could not fetch price for revalidation of signal #{signal_id}")
                        continue
                    
                    if event_type == 'timeout':
                        await self._handle_signal_timeout(
                            signal_id, signal, signal_type, entry, tp, sl,
                            current_price, minutes_elapsed
                        )
                    
                    elif event_type == 'revalidation':
                        await self._handle_signal_revalidation(
                            signal_id, signal, event, signal_type, entry, tp, sl,
                            current_price, minutes_elapsed
                        )
                
        except Exception as e:
            logger.exception("❌ Error in stagnant signal checks")
    
    async def _handle_signal_timeout(
        self,
        signal_id: int,
        signal: Dict,
        signal_type: str,
        entry: float,
        tp: float,
        sl: float,
        current_price: float,
        minutes_elapsed: float
    ):
        """Handle signal timeout."""
        db = self.runtime.db
        
        current_indicators = None
        original_indicators = signal.get('original_indicators_json') or {}
        
        try:
            validation = await self.signal_engine.perform_revalidation(signal)
            if validation:
                current_indicators = validation.get('current_indicators', {})
        except Exception as e:
            logger.warning(f"Could not fetch current indicators for timeout: {e}")
        
        ai_message = generate_timeout_message(
            signal_id=signal_id,
            signal_type=signal_type,
            minutes_elapsed=minutes_elapsed,
            current_price=current_price,
            entry_price=entry,
            tp_price=tp,
            sl_price=sl,
            current_indicators=current_indicators,
            original_indicators=original_indicators
        )
        
        success = await self.messenger.post_signal_timeout(
            signal_id=signal_id,
            message=ai_message,
            current_price=current_price,
            entry_price=entry
        )
        
        if success:
            db.update_signal_timeout_notified(signal_id, tenant_id=self.tenant_id)
            
            if signal_type == 'BUY':
                pips = round((current_price - entry) * 100, 1)
            else:
                pips = round((entry - current_price) * 100, 1)
            
            final_status = 'won' if pips > 0 else 'expired'
            self.runtime.update_forex_signal_status(signal_id, final_status, pips, current_price)
            self.signal_engine.load_active_strategy()
            logger.info(f"✅ Posted close advisory for signal #{signal_id} after {minutes_elapsed/60:.1f}h (status: {final_status})")
    
    async def _handle_signal_revalidation(
        self,
        signal_id: int,
        signal: Dict,
        event: Dict,
        signal_type: str,
        entry: float,
        tp: float,
        sl: float,
        current_price: float,
        minutes_elapsed: float
    ):
        """Handle signal revalidation."""
        db = self.runtime.db
        
        validation = await self.signal_engine.perform_revalidation(signal)
        
        if validation:
            thesis_status = validation['status']
            reasons = validation['reasons']
            previous_status = event.get('current_thesis_status', 'intact')
            
            should_post = False
            if thesis_status != previous_status:
                should_post = True
                logger.info(f"Thesis status changed: {previous_status} -> {thesis_status}")
            elif thesis_status == 'intact':
                logger.info(f"Signal #{signal_id} thesis still intact - no update needed")
            else:
                logger.info(f"Signal #{signal_id} thesis still {thesis_status} - skipping duplicate message")
            
            db.update_signal_revalidation(signal_id, thesis_status, f"Check: {thesis_status}", tenant_id=self.tenant_id)
            
            if should_post:
                ai_message = generate_revalidation_message(
                    signal_id=signal_id,
                    signal_type=signal_type,
                    thesis_status=thesis_status,
                    reasons=reasons,
                    minutes_elapsed=minutes_elapsed,
                    current_price=current_price,
                    entry_price=entry,
                    tp_price=tp,
                    sl_price=sl
                )
                
                success = await self.messenger.post_revalidation_update(
                    signal_id=signal_id,
                    thesis_status=thesis_status,
                    message=ai_message,
                    current_price=current_price,
                    entry_price=entry
                )
                
                if success:
                    db.update_signal_revalidation(
                        signal_id, thesis_status,
                        f"Revalidation: {ai_message[:100]}",
                        tenant_id=self.tenant_id
                    )
                    
                    if thesis_status == 'broken':
                        if signal_type == 'BUY':
                            pips = round((current_price - entry) * 100, 1)
                        else:
                            pips = round((entry - current_price) * 100, 1)
                        
                        final_status = 'won' if pips > 0 else 'expired'
                        self.runtime.update_forex_signal_status(signal_id, final_status, pips, current_price)
                        self.signal_engine.load_active_strategy()
                        logger.info(f"Signal #{signal_id} closed due to broken thesis (status: {final_status})")
