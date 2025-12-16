"""
Journey scheduler - background job for delayed message sending.
"""
import threading
import time
from datetime import datetime
from typing import Callable, Optional
from core.logging import get_logger

logger = get_logger(__name__)

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False
_scheduler_lock = threading.Lock()


def start_journey_scheduler(send_message_fn: Callable[[int, str, str], bool], 
                             interval_seconds: int = 30):
    """
    Start the journey message scheduler in a background thread.
    
    Args:
        send_message_fn: Function to send Telegram messages
                        Signature: (chat_id: int, text: str, bot_id: str) -> bool
        interval_seconds: How often to check for due messages
    """
    global _scheduler_thread, _scheduler_running
    
    with _scheduler_lock:
        if _scheduler_running:
            logger.warning("Journey scheduler already running")
            return
        
        _scheduler_running = True
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(send_message_fn, interval_seconds),
            daemon=True,
            name="JourneyScheduler"
        )
        _scheduler_thread.start()
        logger.info(f"Journey scheduler started (interval={interval_seconds}s)")


def stop_journey_scheduler():
    """Stop the journey scheduler."""
    global _scheduler_running
    
    with _scheduler_lock:
        _scheduler_running = False
        logger.info("Journey scheduler stopped")


def _scheduler_loop(send_message_fn: Callable, interval_seconds: int):
    """Main scheduler loop."""
    global _scheduler_running
    
    while _scheduler_running:
        try:
            process_due_messages(send_message_fn)
        except Exception as e:
            logger.exception(f"Error in journey scheduler loop: {e}")
        
        time.sleep(interval_seconds)


def process_due_messages(send_message_fn: Callable[[int, str, str], bool]) -> int:
    """
    Process all due scheduled messages.
    
    Args:
        send_message_fn: Function to send Telegram messages
        
    Returns:
        Number of messages processed
    """
    from . import repo
    from .engine import JourneyEngine
    
    messages = repo.fetch_due_scheduled_messages(limit=50)
    
    if not messages:
        return 0
    
    logger.info(f"Processing {len(messages)} due journey messages")
    
    engine = JourneyEngine(send_message_fn=send_message_fn)
    processed = 0
    
    for msg in messages:
        try:
            success = _send_scheduled_message(msg, send_message_fn, engine)
            
            if success:
                repo.mark_scheduled_message_sent(msg['id'])
                processed += 1
            else:
                repo.mark_scheduled_message_failed(msg['id'], "Send failed")
                
        except Exception as e:
            logger.exception(f"Error processing scheduled message {msg['id']}: {e}")
            repo.mark_scheduled_message_failed(msg['id'], str(e))
    
    logger.info(f"Processed {processed}/{len(messages)} journey messages")
    return processed


def _get_tenant_send_fn(tenant_id: str) -> Callable[[int, str, str], bool]:
    """
    Get a send message function for a specific tenant.
    Uses tenant's configured message bot from database.
    
    Raises:
        BotNotConfiguredError: If no message bot configured for tenant
    """
    import requests
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
    
    try:
        creds = get_bot_credentials(tenant_id, 'message')
        bot_token = creds['bot_token']
    except BotNotConfiguredError as e:
        logger.error(f"Message bot not configured for tenant {tenant_id}: {e}")
        bot_token = None
    
    def send_fn(chat_id: int, text: str, bot_id: str) -> bool:
        if not bot_token:
            logger.error(f"No bot token available for tenant {tenant_id}")
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
                logger.error(f"Telegram API error: {response.text}")
                return False
        except Exception as e:
            logger.exception(f"Error sending scheduled message: {e}")
            return False
    
    return send_fn


def _send_scheduled_message(msg: dict, send_message_fn: Callable, engine) -> bool:
    """
    Send a single scheduled message and advance the journey.
    
    Args:
        msg: Scheduled message dict
        send_message_fn: Fallback function to send Telegram messages
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
        logger.error(f"Scheduled message {msg['id']} has no tenant_id, skipping")
        return False
    
    tenant_send_fn = _get_tenant_send_fn(tenant_id)
    
    if text:
        success = tenant_send_fn(chat_id, text, bot_id)
        if not success:
            logger.error(f"Failed to send scheduled message to chat {chat_id}")
            return False
    
    session = repo.get_session_by_id(msg['session_id'])
    if not session:
        logger.error(f"Session {msg['session_id']} not found for scheduled message")
        return True
    
    if session['tenant_id'] != msg['tenant_id']:
        logger.error(f"Tenant mismatch: session={session['tenant_id']}, message={msg['tenant_id']}")
        return False
    
    step = repo.get_step_by_id(msg['step_id'])
    if not step:
        logger.error(f"Step {msg['step_id']} not found for scheduled message")
        return True
    
    if step_type == 'message':
        repo.update_session_status(session['id'], 'active')
        repo.update_session_current_step(session['id'], step['id'])
        
        next_step = repo.get_next_step(session['journey_id'], step['step_order'])
        if next_step:
            updated_session = repo.get_session_by_id(session['id'])
            if updated_session:
                engine._advance_to_next_step(updated_session, step, bot_id)
        else:
            repo.update_session_status(session['id'], 'completed')
            logger.info(f"Journey completed for session {session['id']} after scheduled message")
    
    elif step_type == 'question':
        repo.update_session_status(session['id'], 'active')
        repo.update_session_current_step(session['id'], step['id'])
    
    return True


def is_scheduler_running() -> bool:
    """Check if the scheduler is running."""
    return _scheduler_running
