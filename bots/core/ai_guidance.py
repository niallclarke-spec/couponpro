"""
AI Guidance System
Generates intelligent trade guidance using OpenAI
Provides breakeven recommendations, mid-trade updates, and close guidance

Voice: Markus-aligned VIP-desk voice — quiet certainty, no emojis, no hype.
Single voice across the brand (FREE channel hypechat + VIP mid-trade updates).
"""
import os
from typing import Dict, Any, Optional
from openai import OpenAI


# Shared system prompt for every AI call in this module so all VIP-channel
# trade updates speak in the same Markus-aligned voice. Mirrors the bans
# enforced in domains/hypechat/service.py SYSTEM_PROMPT.
_VIP_DESK_VOICE = (
    "You write VIP-channel trade updates for a XAU/USD desk. "
    "Voice: quiet certainty. Calm, restrained, low-volume. "
    "Periods, not exclamation marks. NO emojis. NO hype words "
    "(massive, insane, monster, parabolic, smashed, crushed). "
    "NO shame words (sidelines, spectator, 'watching from outside'). "
    "Real-trader cadence — short lines, sentence fragments OK. "
    "Reference the technical read (RSI, EMA, ADX, the pullback, the breakout) "
    "when it fits. Never invent prices or numbers — only use what's given."
)


class AIGuidance:
    """
    Generates AI-powered trade guidance messages
    Uses OpenAI for intelligent analysis and recommendations
    """
    
    def __init__(self):
        self.client = None
        try:
            api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
            if api_key:
                self.client = OpenAI(api_key=api_key)
        except Exception as e:
            print(f"[AI GUIDANCE] OpenAI not available: {e}")
    
    def generate_breakeven_guidance(self, signal_data: Dict[str, Any]) -> str:
        """
        Generate guidance message for breakeven protection
        
        Args:
            signal_data: Dict with signal_type, entry, current_price, current_pips, etc.
        """
        signal_type = signal_data['signal_type']
        entry = signal_data['entry']
        current_price = signal_data['current_price']
        current_pips = signal_data['current_pips']
        hours_elapsed = signal_data['hours_elapsed']
        
        if self.client:
            try:
                prompt = f"""Live trade — running {hours_elapsed:.1f} hours, no TP or SL hit yet.

Trade details:
- Direction: {signal_type}
- Entry: ${entry:.2f}
- Current Price: ${current_price:.2f}
- Current P/L: {current_pips:+.2f} pips

We are moving the stop loss to breakeven (entry price) — the trade goes risk-free from here.

Write a 2-3 sentence update in the Markus voice that names the SL-to-breakeven move and what it protects. Quiet certainty. No emojis."""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": _VIP_DESK_VOICE},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                print(f"[AI GUIDANCE] OpenAI error: {e}")
        
        if current_pips > 0:
            return f"Trade Update: {signal_type} trade at ${entry:.2f} is currently {current_pips:+.2f} pips. After {hours_elapsed:.1f} hours, moving SL to breakeven to lock in gains."
        else:
            return f"Trade Update: {signal_type} trade at ${entry:.2f} is currently {current_pips:+.2f} pips. After {hours_elapsed:.1f} hours, moving SL to breakeven to limit risk."
    
    def generate_mid_trade_update(self, signal_data: Dict[str, Any]) -> str:
        """
        Generate mid-trade status update (at 2 hours)
        """
        signal_type = signal_data['signal_type']
        entry = signal_data['entry']
        current_price = signal_data['current_price']
        current_pips = signal_data['current_pips']
        hours_elapsed = signal_data['hours_elapsed']
        
        if self.client:
            try:
                prompt = f"""Mid-trade status check.

Trade details:
- Direction: {signal_type}
- Entry: ${entry:.2f}
- Current Price: ${current_price:.2f}
- Current P/L: {current_pips:+.2f} pips
- Time in trade: {hours_elapsed:.1f} hours

Write a 1-2 sentence status update in the Markus voice. Where price sits vs entry, the read still holding. Quiet certainty. No emojis."""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": _VIP_DESK_VOICE},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=100,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                print(f"[AI GUIDANCE] OpenAI error: {e}")
        
        return f"Status Update: {signal_type} @ ${entry:.2f} | Current: ${current_price:.2f} ({current_pips:+.2f} pips) | Holding position."
    
    def generate_close_message(self, signal_data: Dict[str, Any]) -> str:
        """
        Generate message for trade close (TP hit, SL hit, or timeout)
        """
        action = signal_data['action']
        signal_type = signal_data['signal_type']
        entry = signal_data['entry']
        exit_price = signal_data['exit_price']
        pips = signal_data['pips']
        status = signal_data['status']
        
        if self.client:
            try:
                if action == 'tp_hit':
                    nuance = "Quiet certainty, mild satisfaction — the read worked, the process held. No celebration theatrics."
                    context = "Take Profit hit — clean execution."
                elif action == 'sl_hit':
                    nuance = "Composed, matter-of-fact. Risk was planned and respected. Onwards to the next setup."
                    context = "Stop Loss hit — risk was managed properly."
                else:
                    nuance = "Matter-of-fact, no drama. The clock ran out, the trade is closed."
                    context = f"Trade closed at 5-hour timeout with {pips:+.2f} pips."

                prompt = f"""Trade close — write a 2-3 sentence close note in the Markus voice.

Trade result:
- Direction: {signal_type}
- Entry: ${entry:.2f}
- Exit: ${exit_price:.2f}
- Result: {pips:+.2f} pips ({status.upper()})
- Context: {context}

Tone nuance: {nuance}
Quiet certainty. No emojis. No hype. Brief look-forward to the next setup is fine."""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": _VIP_DESK_VOICE},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=120,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                print(f"[AI GUIDANCE] OpenAI error: {e}")
        
        if action == 'tp_hit':
            return f"Take Profit Hit! {signal_type} @ ${entry:.2f} closed at ${exit_price:.2f} for +{pips:.2f} pips."
        elif action == 'sl_hit':
            return f"Stop Loss Hit. {signal_type} @ ${entry:.2f} closed at ${exit_price:.2f} for {pips:.2f} pips. Risk was managed."
        else:
            result_word = "profit" if pips > 0 else "loss"
            return f"Trade Closed (Timeout). {signal_type} @ ${entry:.2f} closed at ${exit_price:.2f} for {pips:+.2f} pips {result_word}."
    
    def generate_daily_recap(self, stats: Dict[str, Any]) -> str:
        """Generate AI-powered daily recap"""
        if self.client:
            try:
                prompt = f"""Generate a professional daily trading recap. Stats:
- Signals: {stats.get('total_signals', 0)}
- Wins: {stats.get('wins', 0)}
- Losses: {stats.get('losses', 0)}  
- Net Pips: {stats.get('net_pips', 0):+.2f}
- Win Rate: {stats.get('win_rate', 0):.1f}%

Write 3-4 sentences summarizing performance. Professional tone, no emojis."""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[AI GUIDANCE] OpenAI error: {e}")
        
        return None
    
    def generate_weekly_recap(self, stats: Dict[str, Any]) -> str:
        """Generate AI-powered weekly recap"""
        if self.client:
            try:
                prompt = f"""Generate a professional weekly trading recap. Stats:
- Total Signals: {stats.get('total_signals', 0)}
- Wins: {stats.get('wins', 0)}
- Losses: {stats.get('losses', 0)}
- Net Pips: {stats.get('net_pips', 0):+.2f}
- Win Rate: {stats.get('win_rate', 0):.1f}%
- Best Day: {stats.get('best_day', 'N/A')}

Write 4-5 sentences summarizing the week's performance. Professional, analytical tone. No emojis."""

                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"[AI GUIDANCE] OpenAI error: {e}")
        
        return None


ai_guidance = AIGuidance()
