"""
AI message generator for forex signals using OpenAI
Creates motivational celebration messages and performance recaps
"""
import os
from openai import OpenAI
from db import get_forex_signals_by_period, get_forex_stats_by_period

client = OpenAI(
    api_key=os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY'),
    base_url=os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
)

def generate_tp_celebration(signal_id, pips_profit, signal_type):
    """
    Generate an AI celebration message for a Take Profit hit
    
    Args:
        signal_id: Database signal ID
        pips_profit: Profit in pips
        signal_type: 'BUY' or 'SELL'
    
    Returns:
        str: AI-generated celebration message
    """
    try:
        prompt = f"""Generate a professional, analytical message for a successful forex trade.

The trade details:
- Signal #{signal_id}
- {signal_type} signal on XAU/USD (Gold)
- Profit: +{pips_profit:.2f} pips

Style: 1-2 sentences. Professional and data-focused. Reference the technical setup, price action, or strategy execution. No emojis. Sound like a professional analyst.

Examples of the tone we want:
- "Signal #{signal_id} executed as planned - RSI divergence and MACD crossover delivered {pips_profit:.0f} pips on the {signal_type} setup."
- "Technical indicators aligned perfectly on this {signal_type} entry, securing {pips_profit:.0f} pips before resistance tested the position."
- "Price action confirmed our analysis - the {signal_type} signal captured {pips_profit:.0f} pips as predicted by the ATR volatility model."

Generate a unique analytical message now:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional, data-driven forex analyst who provides analytical commentary on successful trades. Focus on technical analysis, price action, and strategy execution."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"❌ Error generating AI celebration: {e}")
        return None

def generate_daily_recap():
    """
    Generate AI recap of today's trading signals
    
    Returns:
        str: AI-generated daily recap with signal list
    """
    try:
        signals_today = get_forex_signals_by_period(period='today')
        
        if not signals_today or len(signals_today) == 0:
            return None
        
        signal_summaries = []
        for signal in signals_today:
            status_emoji = {
                'won': '✅',
                'lost': '❌',
                'pending': '⏳',
                'expired': '⏱️'
            }.get(signal['status'], '❓')
            
            signal_type = signal['signal_type']
            pips = signal.get('pips_result', 0)
            
            if pips != 0:
                signal_summaries.append(f"{status_emoji} {signal_type} - {pips:+.2f} pips")
            else:
                signal_summaries.append(f"{status_emoji} {signal_type} - {signal['status']}")
        
        signal_list = "\n".join(signal_summaries)
        
        stats = get_forex_stats_by_period(period='today')
        total_pips = stats.get('total_pips', 0)
        won_signals = stats.get('won_signals', 0)
        total_signals = stats.get('total_signals', 0)
        
        prompt = f"""Generate a professional, data-driven recap commentary for today's forex trading signals.

Today's Results:
{signal_list}

Total Pips: {total_pips:+.2f}
Win/Total: {won_signals}/{total_signals}

Style: 2-3 sentences max. Analytical and professional. Reference market conditions, technical setups, or strategy performance. No emojis.

Generate the analytical recap commentary (don't repeat the numbers, focus on insights):"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional, data-driven forex analyst who provides analytical daily recaps. Focus on market conditions, technical analysis, and strategy performance metrics."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        commentary = response.choices[0].message.content.strip()
        
        return f"\n<b>Today's Signals:</b>\n{signal_list}\n\n{commentary}"
        
    except Exception as e:
        print(f"❌ Error generating daily recap: {e}")
        return None

def generate_weekly_recap():
    """
    Generate AI recap of this week's trading performance
    
    Returns:
        str: AI-generated weekly recap with insights
    """
    try:
        stats = get_forex_stats_by_period(period='week')
        
        if not stats or stats.get('total_signals', 0) == 0:
            return None
        
        total_signals = stats.get('total_signals', 0)
        won_signals = stats.get('won_signals', 0)
        lost_signals = stats.get('lost_signals', 0)
        total_pips = stats.get('total_pips', 0)
        win_rate = (won_signals / total_signals * 100) if total_signals > 0 else 0
        
        prompt = f"""Generate a professional, analytical weekly performance recap for forex trading signals.

This Week's Stats:
- Total Signals: {total_signals}
- Won: {won_signals}
- Lost: {lost_signals}
- Win Rate: {win_rate:.1f}%
- Total Pips: {total_pips:+.2f}

Style: 3-4 sentences. Professional and data-focused. Analyze strategy effectiveness, market conditions, and performance metrics. Reference technical patterns or market behavior. No emojis.

Generate the analytical recap:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional, data-driven forex analyst who provides analytical weekly performance recaps. Focus on strategy metrics, market conditions, and technical analysis patterns."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"❌ Error generating weekly recap: {e}")
        return None
