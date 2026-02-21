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
from datetime import datetime
from typing import Optional

from core.logging import get_logger

logger = get_logger(__name__)

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False
_scheduler_lock = threading.Lock()
_last_dedupe_cleanup = 0


def process_due_messages() -> int:
    """Process all due scheduled messages with rate-limited pacing."""
    from . import repo
    from .engine import JourneyEngine
    
    messages = repo.fetch_due_scheduled_messages(limit=50)
    
    if not messages:
        return 0
    
    logger.info(f"[JOURNEY-SCHEDULER] Processing {len(messages)} due messages")
    
    try:
        from integrations.telegram.user_client import get_client
        uc = get_client('entrylab')
        level = uc._rate.get_level()
    except Exception:
        uc = None
        level = 'normal'
    
    if level == 'hard':
        logger.warning(f"[JOURNEY-SCHEDULER] Hard rate limit hit, deferring {len(messages)} messages back to pending")
        for msg in messages:
            repo.mark_scheduled_message_failed(msg['id'], "Rate limit: daily hard limit reached", reset_to_pending=True)
        return 0
    
    pace_seconds = 5.0 if level == 'soft' else 2.0
    
    engine = JourneyEngine()
    processed = 0
    
    for i, msg in enumerate(messages):
        try:
            try:
                if uc:
                    level = uc._rate.get_level()
                    if level == 'hard':
                        logger.warning(f"[JOURNEY-SCHEDULER] Hit hard limit mid-batch, deferring remaining {len(messages) - i} messages")
                        for remaining_msg in messages[i:]:
                            repo.mark_scheduled_message_failed(remaining_msg['id'], "Rate limit: daily hard limit reached", reset_to_pending=True)
                        break
                    pace_seconds = 5.0 if level == 'soft' else 2.0
            except Exception:
                pass
            
            success = _send_scheduled_message(msg, engine)
            
            if success:
                repo.mark_scheduled_message_sent(msg['id'])
                processed += 1
            else:
                repo.mark_scheduled_message_failed(msg['id'], "Send failed")
                
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Error processing message {msg['id']}: {e}")
            repo.mark_scheduled_message_failed(msg['id'], str(e))
        
        if i < len(messages) - 1:
            time.sleep(pace_seconds)
    
    if processed > 0:
        logger.info(f"[JOURNEY-SCHEDULER] Processed {processed}/{len(messages)} messages (pace={pace_seconds}s, level={level})")
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
    
    engine = JourneyEngine()
    processed = 0
    
    if not timed_out:
        pass
    else:
        logger.info(f"[JOURNEY-SCHEDULER] Processing {len(timed_out)} timed-out sessions")
    
    for session in timed_out:
        try:
            if not session.get('current_step_id'):
                logger.warning(f"[JOURNEY-SCHEDULER] Timeout session {session['id']} has no current step, marking broken")
                repo.mark_session_broken(session['id'], "No current_step_id during timeout")
                continue

            step = repo.get_step_by_id(session['current_step_id'])
            
            # Verify session is still awaiting_reply and step matches
            if session.get('status') != 'awaiting_reply':
                logger.warning(f"[JOURNEY-SCHEDULER] Stale timeout for session {session['id']} - status is {session.get('status')}, skipping")
                continue

            if session.get('current_step_id') != str(step['id']) if step else None:
                logger.warning(f"[JOURNEY-SCHEDULER] Stale timeout for session {session['id']} - step mismatch, skipping")
                continue
            
            if step:
                success = engine.timeout_wait_for_reply(session, step)
                if success:
                    processed += 1
            
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Error processing timeout {session['id']}: {e}")
    
    if processed > 0:
        logger.info(f"[JOURNEY-SCHEDULER] Processed {processed} timeouts")
    
    try:
        inactive_sessions = repo.fetch_inactive_awaiting_sessions(limit=50)
        for session in inactive_sessions:
            try:
                repo.update_session_status(session['id'], 'completed')
                repo.cancel_pending_scheduled_messages(session['id'])
                logger.info(f"[JOURNEY-SCHEDULER] Auto-completed inactive session {session['id']}")
                processed += 1
            except Exception as e:
                logger.exception(f"[JOURNEY-SCHEDULER] Error auto-completing session {session['id']}: {e}")
    except Exception as e:
        logger.exception(f"[JOURNEY-SCHEDULER] Error processing inactivity timeouts: {e}")

    try:
        stale_sessions = repo.fetch_stale_waiting_delay_sessions(stale_after_seconds=60, limit=20)
        for session in stale_sessions:
            try:
                step = repo.get_step_by_id(session['current_step_id']) if session.get('current_step_id') else repo.get_first_step(session['journey_id'])
                if step:
                    journey = repo.get_journey(session['tenant_id'], session['journey_id'])
                    
                    if journey and journey.get('welcome_message') and not session.get('welcome_sent_at'):
                        welcome_text = journey['welcome_message'].replace('{first_name}', '').strip()
                        if welcome_text:
                            engine._send_welcome_with_retry(session['tenant_id'], session['telegram_chat_id'], welcome_text)
                            repo.mark_welcome_sent(session['id'])
                    
                    repo.update_session_status(session['id'], 'active')
                    logger.info(f"[JOURNEY-SCHEDULER] Recovering stale waiting_delay session {session['id']}, executing step {step['id']}")
                    engine.execute_step(session, step, journey.get('bot_id') if journey else None)
                    processed += 1
                else:
                    logger.warning(f"[JOURNEY-SCHEDULER] Stale session {session['id']} has no step to recover, completing")
                    repo.update_session_status(session['id'], 'completed')
            except Exception as e:
                logger.exception(f"[JOURNEY-SCHEDULER] Error recovering stale session {session['id']}: {e}")
    except Exception as e:
        logger.exception(f"[JOURNEY-SCHEDULER] Error processing stale waiting_delay sessions: {e}")

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
    
    session = repo.get_session_by_id(msg['session_id'])
    if not session:
        logger.warning(f"[JOURNEY-SCHEDULER] Stale job {msg['id']} - session not found, cancelling")
        repo.mark_scheduled_message_failed(msg['id'], "Session not found")
        return False

    if session['status'] not in ('active', 'waiting_delay'):
        logger.warning(f"[JOURNEY-SCHEDULER] Stale job {msg['id']} - session status={session['status']}, cancelling")
        repo.mark_scheduled_message_failed(msg['id'], f"Session status is {session['status']}")
        return False

    if session.get('current_step_id') and msg.get('step_id') and session['current_step_id'] != msg['step_id']:
        logger.warning(f"[JOURNEY-SCHEDULER] Stale job {msg['id']} - step mismatch (session={session['current_step_id']}, job={msg['step_id']}), cancelling")
        repo.mark_scheduled_message_failed(msg['id'], "Step mismatch - session advanced")
        return False

    content = msg.get('message_content', {})
    
    if content.get('type') == 'welcome_and_step':
        welcome_text = content.get('welcome_text', '')
        first_name = content.get('first_name', '')
        
        if session.get('welcome_sent_at'):
            logger.info(f"[JOURNEY-SCHEDULER] Welcome already sent for session {msg['session_id']}, skipping to step")
        elif welcome_text:
            engine._send_welcome_with_retry(msg.get('tenant_id'), msg['telegram_chat_id'], welcome_text)
            repo.mark_welcome_sent(msg['session_id'])
        
        step = repo.get_step_by_id(msg['step_id'])
        if step:
            repo.update_session_status(session['id'], 'active')
            repo.update_session_current_step(session['id'], step['id'])
            engine.execute_step(session, step, msg.get('bot_id'))
        return True
    
    text = content.get('text', '')
    step_type = content.get('step_type', 'message')
    
    chat_id = msg['telegram_chat_id']
    bot_id = msg.get('bot_id')
    tenant_id = msg.get('tenant_id')
    
    if not tenant_id:
        logger.error(f"[JOURNEY-SCHEDULER] Message {msg['id']} has no tenant_id")
        return False
    
    if session['tenant_id'] != tenant_id:
        logger.error(f"[JOURNEY-SCHEDULER] Tenant mismatch: session={session['tenant_id']}, msg={tenant_id}")
        return False
    
    if text:
        from integrations.telegram.user_client import get_client
        uc = get_client(tenant_id)
        if not uc.is_connected():
            logger.error(f"[JOURNEY-SCHEDULER] Telethon not connected for tenant={tenant_id}")
            return False
        result = uc.send_message_sync(chat_id, text)
        if not result.get('success'):
            logger.error(f"[JOURNEY-SCHEDULER] Failed to send to chat {chat_id}: {result.get('error')}")
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
    global _scheduler_running, _last_dedupe_cleanup
    
    logger.info(f"[JOURNEY-SCHEDULER] Started (interval={interval_seconds}s)")
    
    while _scheduler_running:
        try:
            process_due_messages()
            process_wait_timeouts()
            
            # Hourly dedupe table cleanup
            now = time.time()
            if now - _last_dedupe_cleanup > 3600:  # Once per hour
                try:
                    from . import repo
                    deleted = repo.cleanup_old_dedupe_records(days=7)
                    if deleted > 0:
                        logger.info(f"[JOURNEY-SCHEDULER] Cleaned up {deleted} old dedupe records")
                    _last_dedupe_cleanup = now
                except Exception as e:
                    logger.exception(f"[JOURNEY-SCHEDULER] Dedupe cleanup error: {e}")
                    _last_dedupe_cleanup = now  # Don't retry immediately on error
        except Exception as e:
            logger.exception(f"[JOURNEY-SCHEDULER] Loop error: {e}")
        
        time.sleep(interval_seconds)
    
    logger.info("[JOURNEY-SCHEDULER] Stopped")


def start_journey_scheduler(interval_seconds: int = 10):
    """
    Start the journey scheduler in a background thread.
    
    Args:
        interval_seconds: How often to check for due messages (default 10s)
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
