"""
AI message generator for forex signals using OpenAI
Creates motivational celebration messages and performance recaps

NOTE: This module now uses integrations.openai.client for the OpenAI client.
All functions remain here for backward compatibility.
"""
from datetime import datetime
from integrations.openai.client import get_openai_client
from db import (
    get_forex_signals_by_period, get_forex_stats_by_period,
    get_recent_signal_streak, get_recent_phrases, add_recent_phrase
)


def _get_client():
    """Get OpenAI client (matches original module-level client behavior)"""
    return get_openai_client()



def get_trading_context():
    """
    Build context data for personalized AI prompts.
    
    Returns:
        dict: Context with streak info, time of day, session info
    """
    now = datetime.utcnow()
    hour = now.hour
    
    # Determine session
    if 8 <= hour < 12:
        session = "London session"
    elif 12 <= hour < 17:
        session = "London/NY overlap"
    elif 17 <= hour < 21:
        session = "NY session"
    else:
        session = "Asian session"
    
    # Get recent streak
    streak = get_recent_signal_streak(limit=5)
    
    streak_context = ""
    if streak['count'] >= 2:
        if streak['type'] == 'win':
            streak_context = f"Currently on a {streak['count']}-win streak. Stay humble but confident."
        else:
            streak_context = f"Coming off {streak['count']} losses. Keep messaging measured and professional, no hype."
    
    return {
        'hour': hour,
        'session': session,
        'streak': streak,
        'streak_context': streak_context,
        'time_of_day': 'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'
    }

def classify_guidance_type(indicator_deltas):
    """
    Classify guidance update based on what indicators have changed.
    
    Guidance types:
    - momentum: RSI, MACD changes
    - volatility: ATR, Bollinger Band changes  
    - structure: Price level testing, EMA changes
    - divergence: Indicator disagreement
    - stagnant: No significant changes
    
    Args:
        indicator_deltas: Dict of indicator name -> delta value
    
    Returns:
        str: Classified guidance type
    """
    if not indicator_deltas:
        return 'stagnant'
    
    # Check for significant moves in each category
    rsi_delta = abs(indicator_deltas.get('rsi', 0))
    macd_delta = abs(indicator_deltas.get('macd', 0))
    atr_delta = abs(indicator_deltas.get('atr', 0))
    adx_delta = abs(indicator_deltas.get('adx', 0))
    stoch_delta = abs(indicator_deltas.get('stochastic', 0))
    
    # Momentum indicators moved significantly
    if rsi_delta > 5 or macd_delta > 0.5:
        return 'momentum'
    
    # Volatility change
    if atr_delta > 1 or adx_delta > 5:
        return 'volatility'
    
    # Check for divergence (indicators moving in opposite directions)
    rsi_direction = indicator_deltas.get('rsi', 0)
    macd_direction = indicator_deltas.get('macd', 0)
    if (rsi_direction > 0 and macd_direction < 0) or (rsi_direction < 0 and macd_direction > 0):
        return 'divergence'
    
    # Structure test (stochastic flip suggests level test)
    if stoch_delta > 10:
        return 'structure'
    
    return 'stagnant'

def get_repetition_avoidance_instruction(phrase_type):
    """
    Get instruction for AI to avoid recently used phrases.
    
    Args:
        phrase_type: Type of message being generated
    
    Returns:
        str: Instruction for AI with phrases to avoid
    """
    recent = get_recent_phrases(phrase_type, limit=5)
    
    if not recent:
        return ""
    
    phrases_to_avoid = ", ".join([f'"{p[:50]}..."' if len(p) > 50 else f'"{p}"' for p in recent[:3]])
    return f"\n\nIMPORTANT: Avoid repeating these recently used phrases/patterns: {phrases_to_avoid}. Use different wording and structure."

def generate_tp_celebration(signal_id, pips_profit, signal_type):
    """
    Generate a short, engaging celebration message for a Take Profit hit.
    Uses emojis and line breaks for a fun, scannable format.
    
    Args:
        signal_id: Database signal ID
        pips_profit: Profit in pips
        signal_type: 'BUY' or 'SELL'
    
    Returns:
        str: Formatted celebration message
    """
    try:
        # Get context for personalization
        context = get_trading_context()
        streak = context['streak']
        
        # Get a short AI-generated line (just the closing thought)
        avoid_instruction = get_repetition_avoidance_instruction('celebration')
        
        prompt = f"""Generate ONE short celebration line (max 8 words) for a winning forex trade.

Context:
- +{pips_profit:.2f} pips profit
- {signal_type} on Gold
{f"- After {streak['count']} losses, this is a relief win!" if streak['type'] == 'loss' and streak['count'] >= 2 else ''}
{f"- Win streak: {streak['count']} in a row!" if streak['type'] == 'win' and streak['count'] >= 2 else ''}

Style: Short, punchy, celebratory. Like "Another profitable trade!" or "Gold delivered today!" or "Clean execution pays off!"
{avoid_instruction}

Generate just the short line, no emojis:"""
        
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write ultra-short celebratory trading messages. Max 8 words. Punchy and fun."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=30,
            temperature=0.9
        )
        
        ai_line = response.choices[0].message.content.strip() if response.choices[0].message.content else "Another profitable trade!"
        
        # Remove any quotes the AI might add
        ai_line = ai_line.strip('"\'')
        
        # Save phrase for future repetition avoidance
        add_recent_phrase('celebration', ai_line)
        
        # Build the formatted message
        direction = "LONG" if signal_type == "BUY" else "SHORT"
        
        message = f"""🎇🎇 XAUUSD 🎇🎇

TP HIT:
✅ +{pips_profit:.2f} pips

{ai_line} 🎊"""
        
        return message
        
    except Exception as e:
        print(f"❌ Error generating AI celebration: {e}")
        # Fallback message
        return f"""🎇🎇 XAUUSD 🎇🎇

TP HIT:
✅ +{pips_profit:.2f} pips

Another profitable trade! 🎊"""

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
        
        response = _get_client().chat.completions.create(
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

def generate_morning_summary(current_price, news_items=None):
    """
    Generate a personalized morning summary for the trading day.
    
    Args:
        current_price: Current gold price
        news_items: List of news items with title and sentiment
    
    Returns:
        str: Short, human-sounding summary (1-2 sentences)
    """
    try:
        news_context = ""
        if news_items:
            news_context = "\n".join([f"- {item.get('title', '')} (Sentiment: {item.get('sentiment', 'Neutral')})" for item in news_items])
        else:
            news_context = "No major news this morning."
        
        prompt = f"""Write a short, personal morning message for gold traders. Sound like a friendly trading desk analyst, not a robot.

Current Gold Price: ${current_price:.2f}
Today's News:
{news_context}

Style:
- 1-2 short sentences max
- Friendly but professional
- Reference the news/market briefly
- End with encouragement
- NO emojis (those are added separately)
- Sound human, like you're talking to a colleague

Examples of good tone:
"Fed testimony today might bring volatility - stay nimble."
"Dollar weakness overnight is supporting gold, watch for momentum."
"Quiet session ahead, focus on clean setups."

Generate the morning message:"""
        
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a friendly, experienced gold trading analyst giving morning updates to your team. Keep it brief, human, and actionable."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60,
            temperature=0.8
        )
        
        content = response.choices[0].message.content
        return content.strip().strip('"\'') if content else "Stay sharp out there."
        
    except Exception as e:
        print(f"❌ Error generating morning summary: {e}")
        return "Stay sharp out there."

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
        
        response = _get_client().chat.completions.create(
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

def generate_signal_guidance(signal_id, signal_type, progress_percent, guidance_type, current_price, entry_price, tp_price, sl_price, indicator_deltas=None, minutes_open=None):
    """
    Generate short, engaging guidance message with emojis and line breaks.
    
    Args:
        signal_id: Database signal ID
        signal_type: 'BUY' or 'SELL'
        progress_percent: Progress toward TP (positive) or SL (negative)
        guidance_type: 'progress_30', 'breakeven_60', 'decision_85', 'caution_30', 'caution_60'
        current_price: Current market price
        entry_price: Signal entry price
        tp_price: Take profit price
        sl_price: Stop loss price
        indicator_deltas: Optional dict of indicator changes since entry
        minutes_open: Optional minutes since signal opened
    
    Returns:
        str: Formatted guidance message with emojis
    """
    try:
        # Get trading context
        context = get_trading_context()
        tiered_type = classify_guidance_type(indicator_deltas) if indicator_deltas else 'stagnant'
        avoid_instruction = get_repetition_avoidance_instruction('guidance')
        
        abs_progress = abs(progress_percent)
        direction = "LONG" if signal_type == "BUY" else "SHORT"
        # XAU/USD: 1 pip = $0.01, multiply by 100
        pips_move = round((current_price - entry_price) * 100, 1) if signal_type == "BUY" else round((entry_price - current_price) * 100, 1)
        
        # Determine emoji and header based on guidance type
        if 'progress' in guidance_type or 'breakeven' in guidance_type:
            header_emoji = "📈"
            status = "IN PROFIT"
        elif 'caution' in guidance_type or 'decision' in guidance_type:
            header_emoji = "⚠️"
            status = "CAUTION"
        else:
            header_emoji = "📊"
            status = "UPDATE"
        
        # Get short AI line
        prompt = f"""Generate ONE short update line (max 12 words) for an active forex trade.

Context:
- {direction} Gold @ ${entry_price:.2f}
- Now: ${current_price:.2f} ({pips_move:+.2f} pips)
- Progress: {abs_progress:.0f}% toward {'TP' if progress_percent > 0 else 'SL'}
- Indicator movement: {tiered_type}
{f'- Open for {minutes_open} minutes' if minutes_open else ''}

Type: {'Positive momentum update' if progress_percent > 0 else 'Caution/pullback update'}

Style: Short, informative. Like "Momentum building, watching $4200 level" or "RSI cooling off, stay patient" or "Breakeven zone - consider locking gains"
{avoid_instruction}

Generate just the short line:"""
        
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write ultra-short trading updates. Max 12 words. Informative and calm."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=40,
            temperature=0.8
        )
        
        ai_line = response.choices[0].message.content.strip() if response.choices[0].message.content else "Monitoring price action"
        ai_line = ai_line.strip('"\'')
        
        add_recent_phrase('guidance', ai_line)
        
        # Build formatted message
        if 'breakeven' in guidance_type:
            message = f"""{header_emoji} XAUUSD {direction}

{status}:
✅ {pips_move:+.2f} pips ({abs_progress:.0f}% to TP)

🔒 Consider breakeven @ ${entry_price:.2f}

{ai_line}"""
        elif 'caution' in guidance_type or 'decision' in guidance_type:
            message = f"""{header_emoji} XAUUSD {direction}

{status}:
📍 Now @ ${current_price:.2f}
📉 {abs_progress:.0f}% toward SL

{ai_line}"""
        else:
            message = f"""{header_emoji} XAUUSD {direction}

{status}:
📍 Now @ ${current_price:.2f}
✅ {pips_move:+.2f} pips

{ai_line}"""
        
        return message
        
    except Exception as e:
        print(f"❌ Error generating signal guidance: {e}")
        return get_fallback_guidance(guidance_type, signal_type, progress_percent, current_price, entry_price)

def get_fallback_guidance(guidance_type, signal_type, progress_percent, current_price, entry_price):
    """Fallback template messages when AI is unavailable"""
    abs_progress = abs(progress_percent)
    direction = "LONG" if signal_type == "BUY" else "SHORT"
    # XAU/USD: 1 pip = $0.01, multiply by 100
    pips_move = round((current_price - entry_price) * 100, 1) if signal_type == "BUY" else round((entry_price - current_price) * 100, 1)
    
    if 'breakeven' in guidance_type:
        return f"""📈 XAUUSD {direction}

IN PROFIT:
✅ {pips_move:+.2f} pips ({abs_progress:.0f}% to TP)

🔒 Consider breakeven @ ${entry_price:.2f}"""
    
    elif 'caution' in guidance_type or 'decision' in guidance_type:
        return f"""⚠️ XAUUSD {direction}

CAUTION:
📍 Now @ ${current_price:.2f}
📉 {abs_progress:.0f}% toward SL

Monitoring closely"""
    
    return f"""📊 XAUUSD {direction}

UPDATE:
📍 Now @ ${current_price:.2f}
{'+' if pips_move > 0 else ''}{pips_move:.2f} pips"""

def generate_revalidation_message(signal_id, signal_type, thesis_status, reasons, minutes_elapsed, current_price, entry_price, tp_price, sl_price):
    """
    Generate short, engaging revalidation message with emojis and line breaks.
    
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
        str: Formatted revalidation message with emojis
    """
    try:
        direction = "LONG" if signal_type == "BUY" else "SHORT"
        hours_elapsed = minutes_elapsed / 60
        # XAU/USD: 1 pip = $0.01, multiply by 100
        pips_move = round((current_price - entry_price) * 100, 1) if signal_type == "BUY" else round((entry_price - current_price) * 100, 1)
        
        # Determine header based on status
        if thesis_status == 'intact':
            header = "📊 THESIS CHECK"
            status_label = "INTACT"
        elif thesis_status == 'weakening':
            header = "⚠️ THESIS CHECK"
            status_label = "WEAKENING"
        else:
            header = "🚨 THESIS CHECK"
            status_label = "BROKEN"
        
        # Get short AI line for the advice
        reasons_text = reasons[0] if reasons else "Mixed signals"
        avoid_instruction = get_repetition_avoidance_instruction('revalidation')
        
        prompt = f"""Generate ONE short advice line (max 10 words) for a trade thesis update.

Context:
- {direction} Gold, open {hours_elapsed:.1f}h
- Thesis: {thesis_status}
- Issue: {reasons_text}

Style based on status:
- intact: Reassuring, like "Setup still valid, holding" or "Patience - thesis intact"
- weakening: Cautious, like "Tighten stops, watching closely" or "Mixed signals - be ready"
- broken: Urgent, like "Consider exit - thesis broken" or "Time to protect capital"
{avoid_instruction}

Generate just the short line:"""
        
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write ultra-short trading updates. Max 10 words."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=30,
            temperature=0.8
        )
        
        ai_line = response.choices[0].message.content.strip() if response.choices[0].message.content else "Monitoring the setup"
        ai_line = ai_line.strip('"\'')
        
        add_recent_phrase('revalidation', ai_line)
        
        # Format the short reason
        short_reason = reasons[0][:50] if reasons else "Indicators mixed"
        
        # Build formatted message
        message = f"""{header}

XAUUSD {direction}:
⏱️ {hours_elapsed:.1f}h open
📍 {pips_move:+.2f} pips

Status: {status_label}
{f'📋 {short_reason}' if thesis_status != 'intact' else ''}

{ai_line}"""
        
        return message
        
    except Exception as e:
        print(f"❌ Error generating revalidation message: {e}")
        return get_fallback_revalidation(thesis_status, signal_type, minutes_elapsed, reasons, current_price, entry_price)

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
        
        # Calculate P/L - XAU/USD: 1 pip = $0.01, multiply by 100
        if signal_type == 'BUY':
            pips = round((current_price - entry_price) * 100, 1)
        else:
            pips = round((entry_price - current_price) * 100, 1)
        
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

        response = _get_client().chat.completions.create(
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

def get_fallback_revalidation(thesis_status, signal_type, minutes_elapsed, reasons, current_price, entry_price):
    """Fallback template messages for revalidation when AI is unavailable"""
    hours = minutes_elapsed / 60
    direction = "LONG" if signal_type == "BUY" else "SHORT"
    # XAU/USD: 1 pip = $0.01, multiply by 100
    pips_move = round((current_price - entry_price) * 100, 1) if signal_type == "BUY" else round((entry_price - current_price) * 100, 1)
    short_reason = reasons[0][:50] if reasons else "Mixed signals"
    
    if thesis_status == 'intact':
        return f"""📊 THESIS CHECK

XAUUSD {direction}:
⏱️ {hours:.1f}h open
📍 {pips_move:+.2f} pips

Status: INTACT

Setup still valid, holding"""
    
    elif thesis_status == 'weakening':
        return f"""⚠️ THESIS CHECK

XAUUSD {direction}:
⏱️ {hours:.1f}h open
📍 {pips_move:+.2f} pips

Status: WEAKENING
📋 {short_reason}

Tighten stops, watching closely"""
    
    elif thesis_status == 'broken':
        return f"""🚨 THESIS CHECK

XAUUSD {direction}:
⏱️ {hours:.1f}h open
📍 {pips_move:+.2f} pips

Status: BROKEN
📋 {short_reason}

Consider exit - thesis broken"""
    
    return f"""📊 THESIS CHECK

XAUUSD {direction}:
⏱️ {hours:.1f}h open

Monitoring the setup"""

def get_fallback_timeout(signal_type, minutes_elapsed, current_price, entry_price, current_indicators=None):
    """Fallback template message for timeout when AI is unavailable"""
    hours = minutes_elapsed / 60
    # XAU/USD: 1 pip = $0.01, multiply by 100
    if signal_type == 'BUY':
        pips = round((current_price - entry_price) * 100, 1)
    else:
        pips = round((entry_price - current_price) * 100, 1)
    
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
