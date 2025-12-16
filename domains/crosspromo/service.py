"""
Cross Promo Service - Core business logic for cross-promoting VIP signals.
Handles news fetching, message building, and job execution.
"""
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pytz

from core.logging import get_logger
from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
from integrations.telegram.client import send_message, copy_message
from domains.crosspromo import repo

logger = get_logger(__name__)

XAU_KEYWORDS = ['gold', 'xau', 'bullion', 'usd', 'dollar', 'fed', 'rates', 
                'inflation', 'cpi', 'jobs', 'nfp', 'fomc', 'powell', 'treasury']


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
    """
    api_key = os.environ.get('ALPHA_NEWS_API')
    
    if not api_key:
        logger.warning("ALPHA_NEWS_API not set, cannot fetch news")
        return []
    
    try:
        url = f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_monetary&limit=10&apikey={api_key}'
        response = requests.get(url, timeout=10)
        data = response.json()
        
        news_items = []
        
        if 'feed' in data:
            for article in data['feed']:
                title = article.get('title', '').lower()
                if any(kw in title for kw in XAU_KEYWORDS):
                    sentiment = article.get('overall_sentiment_label', 'Neutral')
                    if 'Bullish' in sentiment:
                        emoji = '📈'
                    elif 'Bearish' in sentiment:
                        emoji = '📉'
                    else:
                        emoji = '➡️'
                    
                    news_items.append({
                        'title': article.get('title', '')[:80],
                        'sentiment': sentiment,
                        'emoji': emoji
                    })
                    
                    if len(news_items) >= 2:
                        break
        
        return news_items
        
    except Exception as e:
        logger.exception(f"Error fetching news from Alpha Vantage: {e}")
        return []


def build_morning_news_message(tenant_id: str) -> str:
    """
    Build the morning news message with greeting and XAU/USD summary.
    Returns 3-4 line message text.
    """
    news_items = fetch_xau_news()
    
    if news_items:
        news_lines = [f"{item['emoji']} {item['title']}" for item in news_items]
        news_section = "\n".join(news_lines)
    else:
        news_section = "➡️ Markets steady ahead of key data releases"
    
    message = f"""☀️ Good morning, traders!

📰 What's moving XAU/USD today:
{news_section}

Stay sharp for today's signals."""
    
    return message


def build_vip_soon_message() -> str:
    """Build the 'VIP signals coming soon' message."""
    return "⚡ First signals of the day are about to be sent in the VIP. Join today's session."


def build_congrats_cta_message(cta_url: str) -> str:
    """Build the congratulations + CTA message with HTML link."""
    return f"""✅ Congrats to all VIP members on today's win!

This is the kind of precision you can expect every day in VIP.

👉 Join VIP here: <a href="{cta_url}">{cta_url}</a>"""


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
    
    free_channel_id = settings.get('free_channel_id')
    vip_channel_id = settings.get('vip_channel_id')
    bot_role = settings.get('bot_role', 'signal_bot')
    cta_url = settings.get('cta_url', 'https://entrylab.io/subscribe')
    
    if not free_channel_id:
        return {"success": False, "error": "Free channel ID not configured"}
    
    try:
        credentials = get_bot_credentials(tenant_id, bot_role)
        bot_token = credentials['bot_token']
    except BotNotConfiguredError as e:
        return {"success": False, "error": str(e)}
    
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
        
        result = copy_message(bot_token, vip_channel_id, free_channel_id, int(message_id))
        return result
    
    elif job_type == 'forward_win_followup':
        if not vip_channel_id:
            return {"success": False, "error": "VIP channel ID not configured"}
        
        win_message_id = payload.get('vip_win_message_id')
        if not win_message_id:
            return {"success": False, "error": "Missing vip_win_message_id in payload"}
        
        copy_result = copy_message(bot_token, vip_channel_id, free_channel_id, int(win_message_id))
        if not copy_result.get('success'):
            return copy_result
        
        cta_message = build_congrats_cta_message(cta_url)
        cta_result = send_message(bot_token, free_channel_id, cta_message, parse_mode='HTML')
        
        if not cta_result.get('success'):
            return {"success": False, "error": f"CTA message failed: {cta_result.get('error')}"}
        
        return {"success": True}
    
    else:
        return {"success": False, "error": f"Unknown job type: {job_type}"}


def enqueue_daily_sequence(tenant_id: str) -> Dict[str, Any]:
    """
    Enqueue today's daily sequence (morning_news at 09:00, vip_soon at 10:00).
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
    
    morning_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='morning_news',
        run_at=datetime.utcnow(),
        dedupe_key=f"{tenant_id}|{today_str}|morning_news"
    )
    
    vip_soon_job = repo.enqueue_job(
        tenant_id=tenant_id,
        job_type='vip_soon',
        run_at=datetime.utcnow() + timedelta(hours=1),
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
