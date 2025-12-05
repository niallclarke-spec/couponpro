"""
Signal Generator - generates signals using the active bot strategy
Enforces one-signal-at-a-time rule
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime
from bots.core.bot_manager import bot_manager
from db import (
    create_forex_signal, 
    update_signal_telegram_message_id,
    get_open_signal
)


class SignalGenerator:
    """
    Generates trading signals using the active bot strategy
    Ensures only one signal is open at a time
    """
    
    def __init__(self):
        self.manager = bot_manager
    
    async def generate_signal(self) -> Optional[Dict[str, Any]]:
        """
        Check for and generate a new signal if conditions are met
        
        Returns:
            Signal data dict if signal generated, None otherwise
        """
        if not self.manager.can_generate_signal():
            open_signal = self.manager.get_open_signal()
            if open_signal:
                print(f"[SIGNAL GEN] Signal #{open_signal['id']} still open, waiting...")
            return None
        
        strategy = self.manager.get_active_strategy()
        print(f"[SIGNAL GEN] Using {strategy.name} strategy")
        
        signal_data = await strategy.check_for_signal()
        
        if signal_data:
            signal_id = self._save_signal(signal_data)
            if signal_id:
                signal_data['id'] = signal_id
                print(f"[SIGNAL GEN] Signal #{signal_id} created")
            return signal_data
        
        return None
    
    def _save_signal(self, signal_data: Dict[str, Any]) -> Optional[int]:
        """Save signal to database"""
        try:
            indicators_json = json.dumps(signal_data.get('indicators_used', {}))
            
            signal_id = create_forex_signal(
                signal_type=signal_data['signal_type'],
                pair=signal_data['pair'],
                timeframe=signal_data['timeframe'],
                entry_price=signal_data['entry_price'],
                take_profit=signal_data['take_profit'],
                stop_loss=signal_data['stop_loss'],
                rsi_value=signal_data.get('rsi_value'),
                macd_value=signal_data.get('macd_value'),
                atr_value=signal_data.get('atr_value'),
                bot_type=signal_data.get('bot_type', 'aggressive'),
                indicators_used=indicators_json,
                notes=signal_data.get('notes', '')
            )
            
            return signal_id
        except Exception as e:
            print(f"[SIGNAL GEN] Error saving signal: {e}")
            return None
    
    def update_telegram_message_id(self, signal_id: int, message_id: int) -> bool:
        """Update the Telegram message ID for a signal"""
        try:
            update_signal_telegram_message_id(signal_id, message_id)
            return True
        except Exception as e:
            print(f"[SIGNAL GEN] Error updating message ID: {e}")
            return False


signal_generator = SignalGenerator()
