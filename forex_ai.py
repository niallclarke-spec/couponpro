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
        
        content = response.choices[0].message.content
        return content.strip() if content else None
        
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
        
        stats = get_forex_stats_by_period(period='today') or {}
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
        
        content = response.choices[0].message.content
        commentary = content.strip() if content else "Markets were active today."
        
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
        
        content = response.choices[0].message.content
        return content.strip() if content else None
        
    except Exception as e:
        print(f"❌ Error generating weekly recap: {e}")
        return None

def generate_signal_guidance(signal_id, signal_type, progress_percent, guidance_type, current_price, entry_price, tp_price, sl_price):
    """
    Generate AI guidance message for active signal updates.
    
    Args:
        signal_id: Database signal ID
        signal_type: 'BUY' or 'SELL'
        progress_percent: Progress toward TP (positive) or SL (negative)
        guidance_type: 'progress', 'breakeven', 'caution', 'decision'
        current_price: Current market price
        entry_price: Signal entry price
        tp_price: Take profit price
        sl_price: Stop loss price
    
    Returns:
        str: AI-generated guidance message
    """
    try:
        direction = "in profit" if progress_percent > 0 else "under pressure"
        abs_progress = abs(progress_percent)
        
        context_map = {
            'progress': f"Signal is {abs_progress:.0f}% toward {'target' if progress_percent > 0 else 'stop loss'}. Provide a brief market update.",
            'breakeven': f"Signal has moved {abs_progress:.0f}% toward target. Advise traders to consider moving stop loss to breakeven (entry price) to lock in gains.",
            'caution': f"Price has reversed and is now {abs_progress:.0f}% toward stop loss. Provide cautious guidance without causing panic.",
            'decision': f"Signal is {abs_progress:.0f}% toward stop loss with weakening momentum. Suggest whether to hold or consider early exit."
        }
        
        prompt = f"""Generate a professional, analytical trade update message.

Trade Details:
- Signal #{signal_id} - {signal_type} XAU/USD (Gold)
- Entry: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Take Profit: ${tp_price:.2f}
- Stop Loss: ${sl_price:.2f}
- Status: {direction}

Context: {context_map.get(guidance_type, context_map['progress'])}

Style: 2-3 sentences max. Professional and calm. Reference price levels and technical context. No excessive emojis (1-2 max at start). Sound like a professional analyst giving a brief update.

Generate the update:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional forex analyst providing trade management updates. Be calm, data-focused, and actionable. Never use fear-inducing language."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=120,
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        return content.strip() if content else get_fallback_guidance(guidance_type, signal_type, progress_percent, entry_price)
        
    except Exception as e:
        print(f"❌ Error generating signal guidance: {e}")
        return get_fallback_guidance(guidance_type, signal_type, progress_percent, entry_price)

def get_fallback_guidance(guidance_type, signal_type, progress_percent, entry_price):
    """Fallback template messages when AI is unavailable"""
    abs_progress = abs(progress_percent)
    
    if guidance_type == 'progress':
        if progress_percent > 0:
            return f"📊 Signal Update: Trade is {abs_progress:.0f}% toward target. Momentum remains favorable."
        else:
            return f"📊 Signal Update: Trade is testing support. Monitoring price action closely."
    
    elif guidance_type == 'breakeven':
        return f"🔒 Breakeven Alert: Consider moving stop loss to entry (${entry_price:.2f}) to protect gains."
    
    elif guidance_type == 'caution':
        return f"⚠️ Trade Update: Price has pulled back. Current setup still valid - monitoring for reversal."
    
    elif guidance_type == 'decision':
        return f"📉 Decision Point: Trade under pressure. Consider reducing position or holding with original SL."
    
    return "📊 Signal update: Monitoring position."

def generate_revalidation_message(signal_id, signal_type, thesis_status, reasons, minutes_elapsed, current_price, entry_price, tp_price, sl_price):
    """
    Generate AI message for thesis re-validation updates on stagnant trades.
    
    Args:
        signal_id: Database signal ID
        signal_type: 'BUY' or 'SELL'
        thesis_status: 'intact', 'weakening', or 'broken'
        reasons: List of reasons for the status
        minutes_elapsed: Minutes since signal was posted
        current_price: Current market price
        entry_price: Signal entry price
        tp_price: Take profit price
        sl_price: Stop loss price
    
    Returns:
        str: AI-generated revalidation message
    """
    try:
        hours_elapsed = minutes_elapsed / 60
        reasons_text = "; ".join(reasons) if reasons else "Indicators remain supportive"
        
        status_context = {
            'intact': f"After {hours_elapsed:.1f} hours, technical indicators still support the original trade thesis. The trade is consolidating but setup remains valid.",
            'weakening': f"After {hours_elapsed:.1f} hours, some technical indicators are showing mixed signals. The original thesis may be weakening. Reasons: {reasons_text}",
            'broken': f"After {hours_elapsed:.1f} hours, key technical indicators have reversed against the trade. The original thesis appears invalid. Reasons: {reasons_text}"
        }
        
        action_guidance = {
            'intact': "Provide a calm status update. Reassure traders that the setup is still valid and to hold positions.",
            'weakening': "Advise traders to monitor closely and consider tightening stops or reducing position size.",
            'broken': "Recommend closing the position or taking protective action immediately. Be direct but professional."
        }
        
        prompt = f"""Generate a professional trade status message based on indicator re-validation.

Trade Details:
- Signal #{signal_id} - {signal_type} XAU/USD (Gold)
- Entry: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Take Profit: ${tp_price:.2f}
- Stop Loss: ${sl_price:.2f}
- Time in Trade: {hours_elapsed:.1f} hours
- Thesis Status: {thesis_status.upper()}

Context: {status_context.get(thesis_status, status_context['intact'])}

Guidance: {action_guidance.get(thesis_status, action_guidance['intact'])}

Style: 2-3 sentences max. Professional and analytical. Reference the indicator analysis. Use appropriate emoji at start based on status:
- Intact: 📊 (neutral/informational)
- Weakening: ⚠️ (caution)
- Broken: 🚨 (alert/action needed)

Generate the message:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional forex analyst providing trade thesis updates. Be calm, data-focused, and provide clear actionable guidance based on technical analysis."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        return content.strip() if content else get_fallback_revalidation(thesis_status, signal_type, minutes_elapsed, reasons, entry_price)
        
    except Exception as e:
        print(f"❌ Error generating revalidation message: {e}")
        return get_fallback_revalidation(thesis_status, signal_type, minutes_elapsed, reasons, entry_price)

def generate_timeout_message(signal_id, signal_type, minutes_elapsed, current_price, entry_price, tp_price, sl_price, current_indicators=None, original_indicators=None):
    """
    Generate AI message recommending position closure with technical justification.
    
    Args:
        signal_id: Database signal ID
        signal_type: 'BUY' or 'SELL'
        minutes_elapsed: Minutes since signal was posted
        current_price: Current market price
        entry_price: Signal entry price
        tp_price: Take profit price
        sl_price: Stop loss price
        current_indicators: Current indicator values (optional)
        original_indicators: Original indicator values at entry (optional)
    
    Returns:
        str: AI-generated close recommendation with technical reasoning
    """
    try:
        hours_elapsed = minutes_elapsed / 60
        
        # Calculate P/L
        if signal_type == 'BUY':
            pips = round(current_price - entry_price, 2)
        else:
            pips = round(entry_price - current_price, 2)
        
        pips_status = f"+{pips}" if pips > 0 else str(pips)
        
        # Build technical analysis context
        tech_context = ""
        if current_indicators:
            rsi = current_indicators.get('rsi')
            macd = current_indicators.get('macd')
            adx = current_indicators.get('adx')
            stoch = current_indicators.get('stochastic')
            
            tech_context = f"""
Current Technical Indicators:
- RSI: {rsi:.2f if rsi else 'N/A'} {"(neutral zone)" if rsi and 40 < rsi < 60 else "(overbought)" if rsi and rsi > 70 else "(oversold)" if rsi and rsi < 30 else ""}
- MACD: {macd:.4f if macd else 'N/A'} {"(bearish)" if macd and macd < 0 else "(bullish)" if macd and macd > 0 else ""}
- ADX: {adx:.2f if adx else 'N/A'} {"(weak trend)" if adx and adx < 20 else "(moderate trend)" if adx and adx < 40 else "(strong trend)" if adx else ""}
- Stochastic: {stoch:.2f if stoch else 'N/A'}"""
            
            # Compare to original if available
            if original_indicators:
                orig_rsi = original_indicators.get('rsi')
                orig_macd = original_indicators.get('macd')
                if orig_rsi and rsi:
                    tech_context += f"\n- RSI change: {orig_rsi:.2f} → {rsi:.2f}"
                if orig_macd and macd:
                    macd_direction = "weakened" if abs(macd) < abs(orig_macd) else "strengthened"
                    tech_context += f"\n- MACD momentum has {macd_direction}"
        
        prompt = f"""Generate a professional trade closure advisory with technical justification.

Trade Details:
- Signal #{signal_id} - {signal_type} XAU/USD (Gold)
- Entry: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Take Profit: ${tp_price:.2f} (not reached)
- Stop Loss: ${sl_price:.2f} (not reached)
- Time in Trade: {hours_elapsed:.1f} hours
- Current P/L: {pips_status} pips
{tech_context}

Context: After {hours_elapsed:.1f} hours, price has consolidated without clear direction. The original momentum has dissipated.

Your task: Recommend closing the position. Justify with technical analysis (momentum loss, neutral RSI, weak ADX, etc). Do NOT mention "timeout" or "time limit" - focus purely on technical reasons why the trade setup is no longer valid.

Style: 2-3 sentences. Professional, analytical. Start with 🔔 emoji. Reference specific indicators. Clearly recommend closing at current price.

Generate the message:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional forex analyst. Provide clear trade closure recommendations based on technical analysis. Never mention time limits - only technical reasons."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        return content.strip() if content else get_fallback_timeout(signal_type, minutes_elapsed, current_price, entry_price, current_indicators)
        
    except Exception as e:
        print(f"❌ Error generating timeout message: {e}")
        return get_fallback_timeout(signal_type, minutes_elapsed, current_price, entry_price, current_indicators)

def get_fallback_revalidation(thesis_status, signal_type, minutes_elapsed, reasons, entry_price):
    """Fallback template messages for revalidation when AI is unavailable"""
    hours = minutes_elapsed / 60
    reasons_text = "; ".join(reasons[:2]) if reasons else ""
    
    if thesis_status == 'intact':
        return f"📊 Trade Status ({hours:.1f}h): Indicators still support {signal_type} thesis. Trade consolidating - setup remains valid. Hold position."
    
    elif thesis_status == 'weakening':
        return f"⚠️ Trade Status ({hours:.1f}h): Some indicators showing mixed signals{': ' + reasons_text if reasons_text else ''}. Consider tightening stops or reducing position."
    
    elif thesis_status == 'broken':
        return f"🚨 Trade Alert ({hours:.1f}h): Technical indicators have reversed{': ' + reasons_text if reasons_text else ''}. Original thesis invalidated - recommend closing position."
    
    return f"📊 Trade Status: Monitoring signal at {hours:.1f} hours."

def get_fallback_timeout(signal_type, minutes_elapsed, current_price, entry_price, current_indicators=None):
    """Fallback template message for timeout when AI is unavailable"""
    hours = minutes_elapsed / 60
    if signal_type == 'BUY':
        pips = round(current_price - entry_price, 2)
    else:
        pips = round(entry_price - current_price, 2)
    
    pips_status = f"+{pips}" if pips > 0 else str(pips)
    
    # Build technical reason
    tech_reason = "momentum has dissipated and price is consolidating"
    if current_indicators:
        rsi = current_indicators.get('rsi')
        adx = current_indicators.get('adx')
        macd = current_indicators.get('macd')
        
        reasons = []
        if rsi and 40 < rsi < 60:
            reasons.append(f"RSI at {rsi:.1f} (neutral)")
        if adx and adx < 20:
            reasons.append(f"ADX at {adx:.1f} (weak trend)")
        if macd:
            direction = "bearish" if macd < 0 else "bullish"
            if (signal_type == 'BUY' and macd < 0) or (signal_type == 'SELL' and macd > 0):
                reasons.append(f"MACD now {direction}")
        
        if reasons:
            tech_reason = ", ".join(reasons)
    
    return f"🔔 Trade Advisory: {tech_reason}. Original {signal_type} setup no longer supported by indicators. Recommend closing at ${current_price:.2f} ({pips_status} pips) to preserve capital."
