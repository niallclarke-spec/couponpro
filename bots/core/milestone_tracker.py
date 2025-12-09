"""
Unified Signal Milestone Tracker

Handles all progress-based notifications for forex signals with a clean, 
simple flow and 90-second cooldown between messages.

Milestones (toward TP1):
- 40%: AI motivational message
- 70%: Celebrate + Move SL to entry

After TP1 hit (toward TP2):
- 50%: Small celebration

After TP2 hit (toward TP3):
- No intermediate milestone, just wait for TP3

Negative movement:
- 60% toward SL: Calm warning (one time only)

TP Hit celebrations handled separately.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from openai import OpenAI

COOLDOWN_SECONDS = 90


class MilestoneTracker:
    """
    Tracks signal milestones and generates appropriate notifications.
    Enforces global 90-second cooldown between all messages.
    """
    
    def __init__(self):
        self.openai_client = None
        try:
            api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
            base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
            if api_key and base_url:
                self.openai_client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            print(f"[MILESTONE] OpenAI client init failed: {e}")
    
    def check_milestones(self, signal: Dict, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Check if a signal has reached a milestone that needs notification.
        
        Args:
            signal: Signal data from database
            current_price: Current market price
            
        Returns:
            Dict with milestone event data or None if no milestone reached
        """
        signal_id = signal['id']
        signal_type = signal['signal_type']
        entry = float(signal['entry_price'])
        tp1 = float(signal['take_profit'])
        tp2 = float(signal.get('take_profit_2') or 0)
        tp3 = float(signal.get('take_profit_3') or 0)
        sl = float(signal['stop_loss'])
        
        tp1_hit = signal.get('tp1_hit', False)
        tp2_hit = signal.get('tp2_hit', False)
        
        last_milestone_at = signal.get('last_milestone_at')
        milestones_sent = signal.get('milestones_sent') or ''
        
        if last_milestone_at:
            if isinstance(last_milestone_at, str):
                last_milestone_at = datetime.fromisoformat(last_milestone_at.replace('Z', '+00:00').replace('+00:00', ''))
            seconds_since = (datetime.utcnow() - last_milestone_at).total_seconds()
            if seconds_since < COOLDOWN_SECONDS:
                return None
        
        is_buy = signal_type == 'BUY'
        
        if is_buy:
            if not tp1_hit:
                tp_distance = tp1 - entry
                sl_distance = entry - sl
                if current_price >= entry:
                    progress_tp = ((current_price - entry) / tp_distance * 100) if tp_distance > 0 else 0
                    progress_sl = 0
                else:
                    progress_tp = 0
                    progress_sl = ((entry - current_price) / sl_distance * 100) if sl_distance > 0 else 0
            elif not tp2_hit and tp2 > 0:
                tp_distance = tp2 - tp1
                progress_tp = ((current_price - tp1) / tp_distance * 100) if tp_distance > 0 else 0
                progress_sl = 0
            else:
                return None
        else:
            if not tp1_hit:
                tp_distance = entry - tp1
                sl_distance = sl - entry
                if current_price <= entry:
                    progress_tp = ((entry - current_price) / tp_distance * 100) if tp_distance > 0 else 0
                    progress_sl = 0
                else:
                    progress_tp = 0
                    progress_sl = ((current_price - entry) / sl_distance * 100) if sl_distance > 0 else 0
            elif not tp2_hit and tp2 > 0:
                tp_distance = tp1 - tp2
                progress_tp = ((tp1 - current_price) / tp_distance * 100) if tp_distance > 0 else 0
                progress_sl = 0
            else:
                return None
        
        progress_tp = min(max(progress_tp, 0), 100)
        progress_sl = min(max(progress_sl, 0), 100)
        
        current_pips = abs(current_price - entry)
        if is_buy:
            current_pips = current_price - entry
        else:
            current_pips = entry - current_price
        
        milestone = None
        milestone_key = None
        
        if not tp1_hit:
            if progress_tp >= 70 and 'tp1_70' not in milestones_sent:
                milestone = 'tp1_70_breakeven'
                milestone_key = 'tp1_70'
            elif progress_tp >= 40 and 'tp1_40' not in milestones_sent:
                milestone = 'tp1_40_motivational'
                milestone_key = 'tp1_40'
            elif progress_sl >= 60 and 'sl_60' not in milestones_sent:
                milestone = 'sl_60_warning'
                milestone_key = 'sl_60'
        elif not tp2_hit and tp2 > 0:
            if progress_tp >= 50 and 'tp2_50' not in milestones_sent:
                milestone = 'tp2_50_celebration'
                milestone_key = 'tp2_50'
        
        if milestone:
            return {
                'signal_id': signal_id,
                'signal_type': signal_type,
                'milestone': milestone,
                'milestone_key': milestone_key,
                'progress_tp': progress_tp,
                'progress_sl': progress_sl,
                'current_price': current_price,
                'current_pips': round(current_pips, 2),
                'entry_price': entry,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'sl': sl,
                'tp1_hit': tp1_hit,
                'tp2_hit': tp2_hit
            }
        
        return None
    
    def generate_milestone_message(self, event: Dict) -> str:
        """
        Generate the appropriate message for a milestone event.
        Uses AI for motivational messages to keep them unique.
        """
        milestone = event['milestone']
        signal_type = event['signal_type']
        current_pips = event['current_pips']
        progress_tp = event['progress_tp']
        entry = event['entry_price']
        current_price = event['current_price']
        
        direction = "SHORT" if signal_type == "SELL" else "LONG"
        
        if milestone == 'tp1_40_motivational':
            return self._generate_40_percent_message(event)
        
        elif milestone == 'tp1_70_breakeven':
            return self._generate_70_percent_message(event)
        
        elif milestone == 'tp2_50_celebration':
            return self._generate_tp2_50_message(event)
        
        elif milestone == 'sl_60_warning':
            return self._generate_sl_warning_message(event)
        
        return ""
    
    def _generate_40_percent_message(self, event: Dict) -> str:
        """Generate AI-powered motivational message at 40% toward TP1"""
        current_pips = event['current_pips']
        progress = event['progress_tp']
        signal_type = event['signal_type']
        direction = "short" if signal_type == "SELL" else "long"
        
        if self.openai_client:
            try:
                # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
                # do not change this unless explicitly requested by the user
                response = self.openai_client.chat.completions.create(
                    model="gpt-5",
                    messages=[{
                        "role": "system",
                        "content": "You are a professional forex trading assistant. Generate a short, motivational 1-2 sentence message for traders. Be positive but professional. No emojis in the text itself. Keep it under 100 characters."
                    }, {
                        "role": "user", 
                        "content": f"Our gold {direction} trade is up +{current_pips:.2f} pips, {progress:.0f}% toward TP1. Generate a unique motivational message."
                    }],
                    max_completion_tokens=60
                )
                ai_message = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[MILESTONE] AI message failed: {e}")
                ai_message = "Trade progressing nicely. Stay focused."
        else:
            ai_message = "Trade progressing nicely. Stay focused."
        
        return f"""📈 <b>Signal Update</b>

✅ +{current_pips:.2f} pips ({progress:.0f}% to TP1)

{ai_message}"""
    
    def _generate_70_percent_message(self, event: Dict) -> str:
        """Generate 70% breakeven celebration message"""
        current_pips = event['current_pips']
        entry = event['entry_price']
        
        return f"""⚡ <b>BREAKEVEN ALERT</b>

📊 Price at 70% toward TP1!
💰 Current: <b>+{current_pips:.2f} pips</b>

🔒 Move SL to entry @ ${entry:.2f}

Lock in those gains! 🎯"""
    
    def _generate_tp2_50_message(self, event: Dict) -> str:
        """Generate 50% toward TP2 celebration"""
        current_pips = event['current_pips']
        tp1 = event['tp1']
        tp2 = event['tp2']
        
        return f"""🚀 <b>Momentum Continues!</b>

We're halfway to TP2!

💰 Running profit secured at TP1
📈 Now {event['progress_tp']:.0f}% toward TP2

Keep riding the wave! 🌊"""
    
    def _generate_sl_warning_message(self, event: Dict) -> str:
        """Generate calm warning when 60% toward SL"""
        current_pips = event['current_pips']
        
        return f"""📊 <b>Trade Update</b>

Trade in drawdown. {abs(current_pips):.2f} pips from entry.

Levels holding. Stay patient.

Risk is managed. 🔒"""
    
    def generate_tp1_celebration(self, signal_type: str, pips: float, remaining_pct: int = 0) -> str:
        """Generate TP1 hit celebration message"""
        if remaining_pct > 0:
            return f"""🎉 <b>TP1 HIT!</b>

+{pips:.2f} pips secured! 💰

🔄 {remaining_pct}% still riding to TP2

Well played! 🎯"""
        else:
            return f"""🎉 <b>TARGET HIT!</b>

+{pips:.2f} pips profit! 💰

Trade closed successfully.

Great execution! 🏆"""
    
    def generate_tp2_celebration(self, signal_type: str, pips: float, tp1_price: float, remaining_pct: int = 0) -> str:
        """Generate TP2 hit celebration message with SL advice"""
        if remaining_pct > 0:
            return f"""🎉🎉 <b>TP2 HIT!</b>

+{pips:.2f} pips on this leg! 💰💰

🔒 Move SL to TP1 @ ${tp1_price:.2f}

{remaining_pct}% riding to TP3! 🚀"""
        else:
            return f"""🎉🎉 <b>TP2 HIT - TRADE CLOSED!</b>

+{pips:.2f} pips total profit! 💰💰

Excellent execution! 🏆"""
    
    def generate_tp3_celebration(self, signal_type: str, pips: float) -> str:
        """Generate TP3 hit big celebration message"""
        return f"""🎯🎉🎉🎉 <b>TP3 HIT - FULL TARGET!</b> 🎉🎉🎉🎯

💰💰💰 +{pips:.2f} pips profit! 💰💰💰

MAXIMUM GAINS SECURED! 🏆

Congratulations to everyone who held! 

🙌 Outstanding trade! 🙌"""
    
    def generate_sl_hit_message(self, pips_loss: float) -> str:
        """Generate stop loss hit message"""
        return f"""📉 <b>Stop Loss Hit</b>

-{abs(pips_loss):.2f} pips

Risk was managed. 

Onwards to the next opportunity. 💪"""


milestone_tracker = MilestoneTracker()
