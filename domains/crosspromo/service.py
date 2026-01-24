"""
Cross Promo Service - Core business logic for cross-promoting VIP signals.
Handles news fetching, message building, and job execution.
"""
import os
import re
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pytz

from core.logging import get_logger
from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
from integrations.telegram.client import send_message, forward_message
from domains.crosspromo import repo
from db import get_crosspromo_status, update_crosspromo_status, get_today_crosspromo_count

logger = get_logger(__name__)

XAU_PRIMARY_KEYWORDS = ['gold', 'xau', 'bullion', 'precious metal']
XAU_SECONDARY_KEYWORDS = ['usd', 'dollar', 'fed', 'rates', 'inflation', 'cpi', 
                          'jobs', 'nfp', 'fomc', 'powell', 'treasury', 'yields']


KNOWN_NEWS_SOURCES = [
    'Investing.com', 'Reuters', 'Bloomberg', 'CNBC', 'MarketWatch', 
    'Benzinga', 'Yahoo Finance', "Barron's", 'The Wall Street Journal', 
    'WSJ', 'Financial Times', 'FT', 'Kitco', 'DailyFX', 'FXStreet', 
    'ForexLive', 'AP News', 'AFP', 'Dow Jones', 'Nasdaq', 'Morningstar',
    'Seeking Alpha', 'The Motley Fool', 'Business Insider', 'CNBC Pro'
]


def sanitize_news_title(title: str) -> str:
    """
    Strip source attributions and URLs from Alpha Vantage news titles.
    
    Uses conservative patterns to avoid breaking legitimate content:
    - Only strips trailing " - Source", " | Source", " By Source" patterns
    - Only removes known news sources, not arbitrary text
    - Falls back to original if sanitization yields empty result
    
    Examples:
        "SPY Sell Off By Investing.com" -> "SPY Sell Off"
        "Gold rises - Reuters" -> "Gold rises"
        "Fed hikes | Bloomberg" -> "Fed hikes"
        "News here https://example.com more" -> "News here more"
        "Gold By The Numbers" -> "Gold By The Numbers" (preserved - not a source)
    """
    if not title:
        return ""
    
    original = title.strip()
    
    cleaned = re.sub(r'https?://\S+', '', title)
    
    sources_pattern = '|'.join(re.escape(s) for s in KNOWN_NEWS_SOURCES)
    cleaned = re.sub(
        rf'\s*[-–—|]\s*(?:[Bb]y\s+)?({sources_pattern})\s*$',
        '', 
        cleaned, 
        flags=re.IGNORECASE
    )
    cleaned = re.sub(
        rf'\s+[Bb]y\s+({sources_pattern})\s*$',
        '', 
        cleaned, 
        flags=re.IGNORECASE
    )
    
    cleaned = re.sub(r'\s*[-–—|]\s*$', '', cleaned)
    
    cleaned = cleaned.strip()
    
    if not cleaned:
        logger.warning(f"Sanitization yielded empty title, using original: {original[:50]}")
        return original
    
    return cleaned


def is_weekday(tenant_timezone: str = 'UTC') -> bool:
    """Check if today is Monday-Friday in the tenant's timezone."""
    try:
        tz = pytz.timezone(tenant_timezone)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    
    now = datetime.now(tz)
    return now.weekday() < 5


def fetch_xau_news() -> List[Dict[str, Any]]:
    """
    Fetch latest XAU/USD relevant news from Alpha Vantage.
    Returns list of news items, each with title, sentiment, emoji.
    
    Uses weighted keyword matching:
    - Primary keywords (gold, xau, bullion) are prioritized
    - Secondary keywords (fed, inflation, etc.) are fallback
    - Checks both title and summary for better relevance
    """
    api_key = os.environ.get('ALPHA_NEWS_API')
    
    if not api_key:
        logger.warning("ALPHA_NEWS_API not set, cannot fetch news")
        return []
    
    try:
        url = f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=forex,commodities,economy_monetary&limit=15&apikey={api_key}'
        response = requests.get(url, timeout=10)
        data = response.json()
        
        primary_matches = []
        secondary_matches = []
        
        if 'feed' in data:
            for article in data['feed']:
                title = article.get('title', '')
                summary = article.get('summary', '')
                searchable = (title + ' ' + summary).lower()
                
                has_primary = any(kw in searchable for kw in XAU_PRIMARY_KEYWORDS)
                has_secondary = any(kw in searchable for kw in XAU_SECONDARY_KEYWORDS)
                
                if not has_primary and not has_secondary:
                    continue
                
                sentiment = article.get('overall_sentiment_label', 'Neutral')
                if 'Bullish' in sentiment:
                    emoji = '📈'
                elif 'Bearish' in sentiment:
                    emoji = '📉'
                else:
                    emoji = '➡️'
                
                clean_title = sanitize_news_title(title)
                if len(clean_title) > 80:
                    clean_title = clean_title[:77] + '...'
                
                item = {
                    'title': clean_title,
                    'sentiment': sentiment,
                    'emoji': emoji
                }
                
                if has_primary:
                    if len(primary_matches) < 2:
                        primary_matches.append(item)
                else:
                    if len(secondary_matches) < 2:
                        secondary_matches.append(item)
                
                if len(primary_matches) >= 2:
                    break
        
        if primary_matches:
            return primary_matches[:2]
        elif secondary_matches:
            return secondary_matches[:2]
        else:
            return []
        
    except Exception as e:
        logger.exception(f"Error fetching news from Alpha Vantage: {e}")
        return []


def build_morning_news_message(tenant_id: str) -> str:
    """
    Build the morning news message with greeting and XAU/USD summary.
    Returns a concise paragraph summarizing what's affecting gold.
    """
    news_items = fetch_xau_news()
    
    if news_items:
        themes = [item['title'] for item in news_items]
        combined = ' and '.join(themes[:2]) if len(themes) >= 2 else themes[0] if themes else ''
        
        sentiments = [item.get('sentiment', 'Neutral') for item in news_items]
        if any('Bullish' in s for s in sentiments):
            outlook = "supporting gold prices"
        elif any('Bearish' in s for s in sentiments):
            outlook = "putting pressure on gold"
        else:
            outlook = "keeping traders cautious on gold"
        
        summary = f"Today's key focus: {combined}, {outlook}."
    else:
        summary = "Markets are steady ahead of key data releases, keeping gold in a holding pattern."
    
    message = f"""☀️ Good morning, traders!

{summary}"""
    
    return message


def build_vip_soon_message() -> str:
    """Build the 'VIP signals coming soon' message."""
    return "⚡ First signals of the day are about to be sent in the VIP. Join today's session."


def build_congrats_cta_message(cta_url: str) -> str:
    """Build the congratulations + CTA message with HTML link."""
    return f"""✅ Congrats to all VIP members on today's win!

This is the kind of precision you can expect every day in VIP.

👉 <a href="{cta_url}">Join VIP Members – Where Precision Meets Profit</a>"""


def generate_forward_promo_message(pips_secured: float = None, tp_number: int = 1) -> str:
    """
    Generate an AI-powered promotional message for forwarded VIP signals.
    Short, motivational, with emojis - emphasizes this was sent earlier in VIP.
    """
    import os
    from openai import OpenAI
    
    try:
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        
        if not api_key or not base_url:
            return _fallback_promo_message(pips_secured, tp_number)
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        pips_context = f" VIP members just secured {pips_secured:+.0f} pips on this signal." if pips_secured else ""
        
        prompt = f"""Write a SHORT (2-3 lines max) promotional message for a Telegram forex signals channel.

Context: This message will appear AFTER we forward a winning VIP signal to our FREE channel.{pips_context}

Key points to convey:
- This signal was sent earlier in our VIP group
- VIP members are already profiting from signals like this
- Create FOMO to encourage joining VIP
- Use 2-3 relevant emojis (fire, money, chart, rocket, trophy)
- Keep it punchy and motivational
- Don't use hashtags
- Don't mention specific prices or exact times

Example tone: "Another win for our VIP fam! 🔥 This signal was live in VIP hours ago. Our members are stacking pips daily 💰"

Write ONLY the message, nothing else:"""

        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        
        message = response.choices[0].message.content.strip()
        
        if len(message) > 10:
            return message
        else:
            return _fallback_promo_message(pips_secured, tp_number)
            
    except Exception as e:
        logger.warning(f"AI promo message generation failed: {e}")
        return _fallback_promo_message(pips_secured, tp_number)


def _fallback_promo_message(pips_secured: float = None, tp_number: int = 1) -> str:
    """Fallback promo messages when AI is unavailable."""
    import random
    
    messages = [
        "🔥 Another win for VIP! This signal was live in VIP earlier today. Our members are stacking pips daily 💰",
        "💎 VIP members caught this one early! Join us and never miss a winning signal again 🚀",
        "🏆 This is what VIP looks like! Our members had this signal hours ago. Ready to join the winners? 💪",
        "⚡ VIP members are eating GOOD! This signal hit while you were waiting. Time to upgrade? 📈",
        "🎯 Precision signals, real profits! VIP members secured this win earlier. Don't miss the next one 🔥",
    ]
    
    base = random.choice(messages)
    
    if pips_secured and pips_secured > 0:
        base = f"+{pips_secured:.0f} pips secured! " + base
    
    return base


def generate_tp3_hype_message() -> str:
    """
    Generate a short AI-powered hype message for TP3 (full target) hit.
    Falls back to static message if OpenAI fails.
    """
    fallback_messages = [
        "🔥 Full target reached! Another perfect trade in VIP!",
        "🎯 Boom! That's how we do it in VIP! Full TP hit!",
        "💰 Another winner! VIP members just banked gains!",
        "🚀 Clean sweep! All targets hit! That's VIP precision!",
        "✨ Perfect execution! Full profit locked in!"
    ]
    
    import random
    try:
        from openai import OpenAI
        client = OpenAI()
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a hype-man for a forex trading VIP channel. Generate ONE short, exciting celebration message (max 15 words) for hitting a full take-profit target on gold (XAU/USD). Use 1-2 emojis. Be energetic but professional. No hashtags."
                },
                {
                    "role": "user", 
                    "content": "Generate a hype message celebrating a full target hit on gold."
                }
            ],
            max_tokens=50,
            temperature=0.9
        )
        
        content = response.choices[0].message.content
        message = content.strip() if content else random.choice(fallback_messages)
        logger.info(f"AI generated TP3 hype: {message}")
        return message
        
    except Exception as e:
        logger.warning(f"OpenAI hype generation failed, using fallback: {e}")
        import random
        return random.choice(fallback_messages)


def send_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a cross promo job. Returns result dict with success/error.
    
    Job types:
    - morning_news: Send morning greeting + news to free channel
    - vip_soon: Send "signals coming" message to free channel
    - forward_winning_signal: Copy VIP signal to free channel
    - forward_win_followup: Copy VIP win message + send CTA to free channel
    """
    tenant_id = job['tenant_id']
    job_type = job['job_type']
    payload = job.get('payload') or {}
    
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not found"}
    
    if not settings.get('enabled'):
        return {"success": False, "error": "Cross promo is disabled for this tenant"}
    
    bot_role = settings.get('bot_role', 'signal_bot')
    cta_url = settings.get('cta_url', 'https://entrylab.io/subscribe')
    
    try:
        credentials = get_bot_credentials(tenant_id, bot_role)
        bot_token = credentials['bot_token']
        vip_channel_id = credentials.get('vip_channel_id')
        free_channel_id = credentials.get('free_channel_id')
    except BotNotConfiguredError as e:
        return {"success": False, "error": str(e)}
    
    if not vip_channel_id:
        vip_channel_id = settings.get('vip_channel_id')
    if not free_channel_id:
        free_channel_id = settings.get('free_channel_id')
    
    if not free_channel_id:
        return {"success": False, "error": "Free channel ID not configured. Set it in the Connections page under Signal Bot."}
    
    if job_type == 'morning_news':
        message = build_morning_news_message(tenant_id)
        result = send_message(bot_token, free_channel_id, message)
        return result
    
    elif job_type == 'vip_soon':
        message = build_vip_soon_message()
        result = send_message(bot_token, free_channel_id, message)
        return result
    
    elif job_type == 'forward_winning_signal':
        if not vip_channel_id:
            return {"success": False, "error": "VIP channel ID not configured"}
        
        message_id = payload.get('vip_signal_message_id')
        if not message_id:
            return {"success": False, "error": "Missing vip_signal_message_id in payload"}
        
        # Use forward_message to show "Forwarded from VIP Channel" label
        result = forward_message(bot_token, vip_channel_id, free_channel_id, int(message_id))
        return result
    
    elif job_type == 'forward_win_followup':
        if not vip_channel_id:
            return {"success": False, "error": "VIP channel ID not configured"}
        
        win_message_id = payload.get('vip_win_message_id')
        if not win_message_id:
            return {"success": False, "error": "Missing vip_win_message_id in payload"}
        
        # Use forward_message to show "Forwarded from VIP Channel" label
        copy_result = forward_message(bot_token, vip_channel_id, free_channel_id, int(win_message_id))
        if not copy_result.get('success'):
            return copy_result
        
        cta_message = build_congrats_cta_message(cta_url)
        cta_result = send_message(bot_token, free_channel_id, cta_message, parse_mode='HTML')
        
        if not cta_result.get('success'):
            return {"success": False, "error": f"CTA message failed: {cta_result.get('error')}"}
        
        return {"success": True}
    
    elif job_type == 'forward_tp1_sequence':
        # Forward original signal + TP1 hit message to FREE channel (with forwarded from header)
        if not vip_channel_id:
            return {"success": False, "error": "VIP channel ID not configured"}
        
        signal_id = payload.get('signal_id')
        signal_message_id = payload.get('signal_message_id')
        tp1_message_id = payload.get('tp1_message_id')
        pips_secured = payload.get('pips_secured')
        
        if not signal_message_id or not tp1_message_id:
            return {"success": False, "error": "Missing signal_message_id or tp1_message_id"}
        
        # Forward original signal (shows "Forwarded from VIP" with timestamp)
        signal_result = forward_message(bot_token, vip_channel_id, free_channel_id, int(signal_message_id))
        if not signal_result.get('success'):
            return {"success": False, "error": f"Forward signal failed: {signal_result.get('error')}"}
        
        # Forward TP1 hit message
        tp1_result = forward_message(bot_token, vip_channel_id, free_channel_id, int(tp1_message_id))
        if not tp1_result.get('success'):
            return {"success": False, "error": f"Forward TP1 failed: {tp1_result.get('error')}"}
        
        # Send AI-generated promo message after the forwards
        promo_message = generate_forward_promo_message(pips_secured=pips_secured, tp_number=1)
        promo_result = send_message(bot_token, free_channel_id, promo_message)
        if not promo_result.get('success'):
            logger.warning(f"Promo message failed but forwards succeeded: {promo_result.get('error')}")
        
        # Mark signal as cross-promo started
        if signal_id:
            update_crosspromo_status(signal_id, 'started', tenant_id)
        
        logger.info(f"TP1 sequence forwarded with promo: signal_msg={signal_message_id}, tp1_msg={tp1_message_id}")
        return {"success": True}
    
    elif job_type == 'forward_tp3_update':
        # Forward TP3 message + AI hype message
        if not vip_channel_id:
            return {"success": False, "error": "VIP channel ID not configured"}
        
        tp3_message_id = payload.get('tp3_message_id')
        if not tp3_message_id:
            return {"success": False, "error": "Missing tp3_message_id"}
        
        # Forward TP3 hit message
        tp3_result = forward_message(bot_token, vip_channel_id, free_channel_id, int(tp3_message_id))
        if not tp3_result.get('success'):
            return {"success": False, "error": f"Forward TP3 failed: {tp3_result.get('error')}"}
        
        # Generate and send AI hype message
        hype_message = generate_tp3_hype_message()
        hype_result = send_message(bot_token, free_channel_id, hype_message)
        if not hype_result.get('success'):
            logger.warning(f"Hype message failed but TP3 forwarded: {hype_result.get('error')}")
        
        logger.info(f"TP3 update forwarded: tp3_msg={tp3_message_id}")
        return {"success": True}
    
    elif job_type == 'send_cta':
        # Send CTA message and mark signal as cross-promo complete
        signal_id = payload.get('signal_id')
        
        cta_message = build_congrats_cta_message(cta_url)
        cta_result = send_message(bot_token, free_channel_id, cta_message, parse_mode='HTML')
        
        if not cta_result.get('success'):
            return {"success": False, "error": f"CTA message failed: {cta_result.get('error')}"}
        
        # Mark signal as cross-promo complete (prevents further updates)
        if signal_id:
            update_crosspromo_status(signal_id, 'complete', tenant_id)
        
        logger.info(f"CTA sent for signal #{signal_id}, cross-promo complete")
        return {"success": True}
    
    else:
        return {"success": False, "error": f"Unknown job type: {job_type}"}


def enqueue_daily_sequence(tenant_id: str) -> Dict[str, Any]:
    """
    Enqueue today's daily sequence.
    - morning_news: runs immediately when called
    - vip_soon: runs after configured delay (default 45 minutes)
    
    Only works Mon-Fri. Returns result dict.
    """
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    if not settings.get('enabled'):
        return {"success": False, "error": "Cross promo is disabled"}
    
    timezone = settings.get('timezone', 'UTC')
    
    if not is_weekday(timezone):
        return {"success": False, "error": "Daily sequence only runs Monday-Friday"}
    
    try:
        tz = pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    
    now = datetime.now(tz)
    today_str = now.strftime('%Y-%m-%d')
    
    vip_soon_delay = settings.get('vip_soon_delay_minutes', 45)
    
    morning_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='morning_news',
        run_at=datetime.utcnow(),
        dedupe_key=f"{tenant_id}|{today_str}|morning_news"
    )
    
    vip_soon_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='vip_soon',
        run_at=datetime.utcnow() + timedelta(minutes=vip_soon_delay),
        dedupe_key=f"{tenant_id}|{today_str}|vip_soon"
    )
    
    jobs_created = []
    if morning_job:
        jobs_created.append('morning_news')
    if vip_soon_job:
        jobs_created.append('vip_soon')
    
    if not jobs_created:
        return {"success": True, "message": "Jobs already exist for today (dedupe)"}
    
    return {"success": True, "jobs_created": jobs_created}


def enqueue_win_sequence(
    tenant_id: str,
    vip_signal_message_id: int,
    vip_win_message_id: int
) -> Dict[str, Any]:
    """
    Enqueue the win promo sequence:
    - forward_winning_signal immediately
    - forward_win_followup in 60 minutes
    
    Returns result dict.
    """
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    if not settings.get('enabled'):
        return {"success": False, "error": "Cross promo is disabled"}
    
    timezone = settings.get('timezone', 'UTC')
    
    if not is_weekday(timezone):
        return {"success": False, "error": "Win sequence only runs Monday-Friday"}
    
    now = datetime.utcnow()
    
    signal_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='forward_winning_signal',
        run_at=now,
        payload={'vip_signal_message_id': vip_signal_message_id}
    )
    
    followup_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='forward_win_followup',
        run_at=now + timedelta(minutes=60),
        payload={'vip_win_message_id': vip_win_message_id}
    )
    
    jobs_created = []
    if signal_job:
        jobs_created.append('forward_winning_signal')
    if followup_job:
        jobs_created.append('forward_win_followup')
    
    return {"success": True, "jobs_created": jobs_created}


def send_test_morning_message(tenant_id: str) -> Dict[str, Any]:
    """
    Send a test morning message without enqueueing the full flow.
    For preview/testing purposes.
    """
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    free_channel_id = settings.get('free_channel_id')
    bot_role = settings.get('bot_role', 'signal_bot')
    
    if not free_channel_id:
        return {"success": False, "error": "Free channel ID not configured"}
    
    try:
        credentials = get_bot_credentials(tenant_id, bot_role)
        bot_token = credentials['bot_token']
    except BotNotConfiguredError as e:
        return {"success": False, "error": str(e)}
    
    message = build_morning_news_message(tenant_id)
    result = send_message(bot_token, free_channel_id, message)
    
    return result


def get_morning_preview(tenant_id: str) -> str:
    """Get a preview of the morning message without sending."""
    return build_morning_news_message(tenant_id)


def send_test_forward_promo(tenant_id: str, pips_secured: float = 179.0) -> Dict[str, Any]:
    """
    Send a test AI-generated promo message to the free channel.
    Simulates what would be sent after forwarding a winning signal.
    """
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    free_channel_id = settings.get('free_channel_id')
    bot_role = settings.get('bot_role', 'signal_bot')
    
    if not free_channel_id:
        return {"success": False, "error": "Free channel ID not configured"}
    
    try:
        credentials = get_bot_credentials(tenant_id, bot_role)
        bot_token = credentials['bot_token']
    except BotNotConfiguredError as e:
        return {"success": False, "error": str(e)}
    
    promo_message = generate_forward_promo_message(pips_secured=pips_secured, tp_number=1)
    result = send_message(bot_token, free_channel_id, promo_message)
    
    if result.get('success'):
        return {"success": True, "message_sent": promo_message}
    return result


def send_test_cta(tenant_id: str) -> Dict[str, Any]:
    """
    Send a test CTA message with sticker to the free channel.
    For testing the new CTA styling before production.
    
    This endpoint validates the full sticker+CTA presentation.
    If either component fails, the endpoint reports failure.
    """
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    free_channel_id = settings.get('free_channel_id')
    bot_role = settings.get('bot_role', 'signal_bot')
    cta_url = settings.get('cta_url', 'https://entrylab.io/subscribe')
    
    if not free_channel_id:
        return {"success": False, "error": "Free channel ID not configured"}
    
    try:
        credentials = get_bot_credentials(tenant_id, bot_role)
        bot_token = credentials['bot_token']
    except BotNotConfiguredError as e:
        return {"success": False, "error": str(e)}
    
    from integrations.telegram.client import send_sticker
    
    pointing_sticker_id = "CAACAgIAAxkBAAEKb2JlMvKAAb6_AAHm8QYKAAFbQYVxoZEVAAI-EQACh7xQSNmjw1oFCfHqMAQ"
    sticker_result = send_sticker(bot_token, free_channel_id, pointing_sticker_id)
    
    if not sticker_result.get('success'):
        return {"success": False, "error": f"Sticker send failed: {sticker_result.get('error', 'Unknown error')}"}
    
    cta_message = build_congrats_cta_message(cta_url)
    cta_result = send_message(bot_token, free_channel_id, cta_message, parse_mode='HTML')
    
    if not cta_result.get('success'):
        return {"success": False, "error": f"CTA message send failed: {cta_result.get('error', 'Unknown error')}"}
    
    return {"success": True, "sticker_sent": True, "cta_sent": True}


def trigger_tp_crosspromo(
    tenant_id: str,
    signal_id: int,
    tp_number: int,
    signal_message_id: int,
    tp_message_id: int,
    pips_secured: float = None
) -> Dict[str, Any]:
    """
    Trigger cross-promo sequence when a TP is hit.
    
    Rules:
    - Only TP1 and TP3 trigger cross-promo
    - TP1: Forward signal + TP1 message, schedule CTA for 60 mins
    - TP3: Forward TP3 message + AI hype, cancel old CTA, reschedule new CTA
    - Max 1 signal per day
    - If CTA already sent (crosspromo_status='complete'), ignore
    - Only runs Monday-Friday
    
    Args:
        tenant_id: Tenant ID
        signal_id: Signal ID in forex_signals table
        tp_number: 1 or 3 (TP2 is ignored)
        signal_message_id: Original signal's Telegram message ID
        tp_message_id: TP hit notification's Telegram message ID
        pips_secured: Optional pips secured for AI promo message
    
    Returns:
        dict with success status and message
    """
    # Only TP1 and TP3 trigger cross-promo
    if tp_number not in [1, 3]:
        return {"success": False, "skipped": True, "reason": f"TP{tp_number} does not trigger cross-promo"}
    
    # Check settings
    settings = repo.get_settings(tenant_id)
    if not settings:
        return {"success": False, "error": "Cross promo settings not configured"}
    
    if not settings.get('enabled'):
        return {"success": False, "skipped": True, "reason": "Cross promo is disabled"}
    
    timezone = settings.get('timezone', 'UTC')
    
    # Only run Monday-Friday
    if not is_weekday(timezone):
        return {"success": False, "skipped": True, "reason": "Cross promo only runs Monday-Friday"}
    
    # Check signal's current cross-promo status
    status = get_crosspromo_status(signal_id, tenant_id)
    if not status:
        return {"success": False, "error": f"Signal {signal_id} not found"}
    
    current_status = status.get('crosspromo_status', 'none')
    
    # If CTA already sent, ignore all further updates
    if current_status == 'complete':
        logger.info(f"Signal #{signal_id} cross-promo already complete, ignoring TP{tp_number}")
        return {"success": False, "skipped": True, "reason": "Cross-promo already complete for this signal"}
    
    now = datetime.utcnow()
    
    if tp_number == 1:
        # TP1: Check daily limit and start cross-promo sequence
        
        # Check 1 per day limit
        today_count = get_today_crosspromo_count(tenant_id, timezone)
        if today_count >= 1:
            logger.info(f"Daily cross-promo limit reached for {tenant_id} (count={today_count})")
            return {"success": False, "skipped": True, "reason": "Daily cross-promo limit reached"}
        
        # Validate we have the signal message ID
        if not signal_message_id:
            return {"success": False, "error": "Missing signal_message_id for TP1 sequence"}
        
        # Enqueue TP1 sequence (forward signal + TP1 immediately)
        tp1_job = repo.enqueue_job(
            tenant_id=tenant_id,
            job_type='forward_tp1_sequence',
            run_at=now,
            payload={
                'signal_id': signal_id,
                'signal_message_id': signal_message_id,
                'tp1_message_id': tp_message_id,
                'pips_secured': pips_secured
            }
        )
        
        # Schedule CTA for 60 minutes later
        cta_job = repo.enqueue_job(
            tenant_id=tenant_id,
            job_type='send_cta',
            run_at=now + timedelta(minutes=60),
            payload={'signal_id': signal_id},
            dedupe_key=f"{tenant_id}|{signal_id}|cta"
        )
        
        logger.info(f"TP1 cross-promo triggered for signal #{signal_id}")
        return {
            "success": True, 
            "triggered": "tp1_sequence",
            "cta_scheduled_at": (now + timedelta(minutes=60)).isoformat()
        }
    
    elif tp_number == 3:
        # TP3: Only trigger if cross-promo already started (TP1 was hit)
        if current_status != 'started':
            logger.info(f"TP3 hit for signal #{signal_id} but cross-promo not started (status={current_status})")
            return {"success": False, "skipped": True, "reason": "TP3 hit but TP1 cross-promo was never triggered"}
        
        # Cancel existing CTA job and reschedule
        repo.cancel_pending_jobs_by_dedupe(f"{tenant_id}|{signal_id}|cta")
        
        # Enqueue TP3 update (forward TP3 + AI hype)
        tp3_job = repo.enqueue_job(
            tenant_id=tenant_id,
            job_type='forward_tp3_update',
            run_at=now,
            payload={
                'signal_id': signal_id,
                'tp3_message_id': tp_message_id
            }
        )
        
        # Schedule new CTA for 60 minutes after TP3
        cta_job = repo.enqueue_job(
            tenant_id=tenant_id,
            job_type='send_cta',
            run_at=now + timedelta(minutes=60),
            payload={'signal_id': signal_id},
            dedupe_key=f"{tenant_id}|{signal_id}|cta"
        )
        
        logger.info(f"TP3 cross-promo update triggered for signal #{signal_id}, CTA rescheduled")
        return {
            "success": True,
            "triggered": "tp3_update",
            "cta_rescheduled_at": (now + timedelta(minutes=60)).isoformat()
        }
    
    return {"success": False, "error": "Unexpected state"}
