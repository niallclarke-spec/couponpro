"""
Journey Scheduler Worker - Processes delayed messages and wait timeouts.

This module runs as a background worker that:
1. Polls journey_scheduled_messages for due messages
2. Sends messages when scheduled_for <= now
3. Uses FOR UPDATE SKIP LOCKED for idempotency (no double sends)
4. Handles wait_for_reply timeouts

Starts automatically at app boot via bootstrap.py.
"""
import threading
import time
import requests
from datetime import datetime
from typing import Callable, Optional

from core.logging import get_logger
from core.bot_credentials import get_bot_credentials, BotNotConfiguredError

logger = get_logger(__name__)

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False
_scheduler_lock = threading.Lock()


def send_telegram_message(tenant_id: str, chat_id: int, text: str) -> bool:
    """
    Send a Telegram message using tenant's configured message bot.
    
    Args:
        tenant_id: Tenant ID to look up bot credentials
        chat_id: Telegram chat ID
        text: Message text to send
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        creds = get_bot_credentials(tenant_id, 'message_bot')
        bot_token = creds['bot_token']
    except BotNotConfiguredError:
        logger.error(f"[JOURNEY-SCHEDULER] Message Bot not configured for tenant {tenant_id}")
        return False
    
    if not bot_token:
        logger.error(f"[JOURNEY-SCHEDULER] No bot token for tenant {tenant_id}")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }, timeout=10)
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"[JOURNEY-SCHEDULER] Telegram API error: {response.text}")
            return False
    except Exception as e:
        logger.exception(f"[JOURNEY-SCHEDULER] Error sending message: {e}")
        return False


def process_due_messages() -> int:
    """
    Process all due scheduled messages.
    
    Returns:
        Number of messages processed
    """
    from . import repo
    from .engine import JourneyEngine
    
    messages = repo.fetch_due_scheduled_messages(limit=50)
    
    if not messages:
        return 0
    
    logger.info(f"[JOURNEY-SCHEDULER] Processing {len(messages)} due messages")
    
    engine = JourneyEngine()
    processed = 0
    
    for msg in messages:
        try:
            success = _send_scheduled_message(msg, engine)
            
            if success:
                repo.mark_scheduled_message_sent(msg['id'])
                processed += 1
            else:
                repo.mark_scheduled_message_failed(msg['id'], "Send failed")
                
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Error processing message {msg['id']}: {e}")
            repo.mark_scheduled_message_failed(msg['id'], str(e))
    
    if processed > 0:
        logger.info(f"[JOURNEY-SCHEDULER] Processed {processed}/{len(messages)} messages")
    return processed


def process_wait_timeouts() -> int:
    """
    Process sessions waiting for reply that have timed out.
    
    Returns:
        Number of timeouts processed
    """
    from . import repo
    from .engine import JourneyEngine
    
    timed_out = repo.fetch_timed_out_waiting_sessions(limit=50)
    
    if not timed_out:
        return 0
    
    logger.info(f"[JOURNEY-SCHEDULER] Processing {len(timed_out)} timed-out sessions")
    
    engine = JourneyEngine()
    processed = 0
    
    for session in timed_out:
        try:
            step = repo.get_step_by_id(session['current_step_id'])
            if step:
                success = engine.timeout_wait_for_reply(session, step)
                if success:
                    processed += 1
            
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Error processing timeout {session['id']}: {e}")
    
    if processed > 0:
        logger.info(f"[JOURNEY-SCHEDULER] Processed {processed} timeouts")
    return processed


def _send_scheduled_message(msg: dict, engine) -> bool:
    """
    Send a single scheduled message and advance the journey.
    
    Args:
        msg: Scheduled message dict
        engine: JourneyEngine instance
        
    Returns:
        True if sent successfully
    """
    from . import repo
    
    content = msg.get('message_content', {})
    text = content.get('text', '')
    step_type = content.get('step_type', 'message')
    
    chat_id = msg['telegram_chat_id']
    bot_id = msg.get('bot_id')
    tenant_id = msg.get('tenant_id')
    
    if not tenant_id:
        logger.error(f"[JOURNEY-SCHEDULER] Message {msg['id']} has no tenant_id")
        return False
    
    if text:
        success = send_telegram_message(tenant_id, chat_id, text)
        if not success:
            logger.error(f"[JOURNEY-SCHEDULER] Failed to send to chat {chat_id}")
            return False
    
    session = repo.get_session_by_id(msg['session_id'])
    if not session:
        logger.error(f"[JOURNEY-SCHEDULER] Session {msg['session_id']} not found")
        return True
    
    if session['tenant_id'] != tenant_id:
        logger.error(f"[JOURNEY-SCHEDULER] Tenant mismatch: session={session['tenant_id']}, msg={tenant_id}")
        return False
    
    step = repo.get_step_by_id(msg['step_id'])
    if not step:
        logger.error(f"[JOURNEY-SCHEDULER] Step {msg['step_id']} not found")
        return True
    
    repo.update_session_status(session['id'], 'active')
    repo.update_session_current_step(session['id'], step['id'])
    
    if step_type == 'message':
        next_step = repo.get_next_step(session['journey_id'], step['step_order'])
        if next_step:
            updated_session = repo.get_session_by_id(session['id'])
            if updated_session:
                engine._advance_to_next_step(updated_session, step, bot_id)
        else:
            repo.update_session_status(session['id'], 'completed')
            logger.info(f"[JOURNEY-SCHEDULER] Journey completed for session {session['id']}")
    
    elif step_type == 'question':
        pass
    
    elif step_type == 'wait_for_reply':
        config = step.get('config', {})
        timeout_minutes = config.get('timeout_minutes', 0)
        if timeout_minutes > 0:
            repo.set_session_awaiting_reply(session['id'], step['id'], timeout_minutes)
        else:
            repo.set_session_awaiting_reply(session['id'], step['id'], None)
    
    return True


def _scheduler_loop(interval_seconds: int):
    """Main scheduler loop."""
    global _scheduler_running
    
    logger.info(f"[JOURNEY-SCHEDULER] Started (interval={interval_seconds}s)")
    
    while _scheduler_running:
        try:
            process_due_messages()
            process_wait_timeouts()
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Loop error: {e}")
        
        time.sleep(interval_seconds)
    
    logger.info("[JOURNEY-SCHEDULER] Stopped")


def start_journey_scheduler(interval_seconds: int = 30):
    """
    Start the journey scheduler in a background thread.
    
    Args:
        interval_seconds: How often to check for due messages (default 30s)
    """
    global _scheduler_thread, _scheduler_running
    
    with _scheduler_lock:
        if _scheduler_running:
            logger.warning("[JOURNEY-SCHEDULER] Already running")
            return
        
        _scheduler_running = True
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(interval_seconds,),
            daemon=True,
            name="JourneyScheduler"
        )
        _scheduler_thread.start()
        logger.info(f"[JOURNEY-SCHEDULER] Background thread started")


def stop_journey_scheduler():
    """Stop the journey scheduler."""
    global _scheduler_running
    
    with _scheduler_lock:
        _scheduler_running = False
        logger.info("[JOURNEY-SCHEDULER] Stop requested")


def is_scheduler_running() -> bool:
    """Check if the scheduler is running."""
    return _scheduler_running
