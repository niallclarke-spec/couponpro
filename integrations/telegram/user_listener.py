"""
Telethon inbound message listener for Journeys.

Listens for incoming messages on the user client and routes them
to active journey sessions for processing replies.
"""
import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable
from telethon import events
from core.logging import get_logger

logger = get_logger('telethon_listener')

_listeners: Dict[str, bool] = {}
_handlers: Dict[str, Callable] = {}
_MAX_LOCK_CACHE = 1000
_user_locks: OrderedDict = OrderedDict()


def _get_user_lock(chat_id: int) -> asyncio.Lock:
    if chat_id in _user_locks:
        _user_locks.move_to_end(chat_id)
        return _user_locks[chat_id]
    lock = asyncio.Lock()
    _user_locks[chat_id] = lock
    while len(_user_locks) > _MAX_LOCK_CACHE:
        _user_locks.popitem(last=False)
    return lock


async def start_listener(tenant_id: str):
    if _listeners.get(tenant_id):
        logger.info(f"Listener already running for tenant={tenant_id}")
        return

    from integrations.telegram.user_client import get_client
    client = get_client(tenant_id)

    if not client.raw_client or not client.is_connected():
        logger.warning(f"Cannot start listener - client not connected for tenant={tenant_id}")
        return

    tc = client.raw_client

    if not await tc.is_user_authorized():
        logger.warning(f"Cannot start listener - client not authorized for tenant={tenant_id}")
        return

    me = await tc.get_me()
    if not me:
        logger.warning(f"Cannot start listener - get_me() returned None for tenant={tenant_id}")
        return
    my_id = me.id

    @tc.on(events.NewMessage(incoming=True))
    async def _handle_incoming(event):
        try:
            if not event.is_private:
                return

            chat_id = event.chat_id
            sender_id = event.sender_id
            text = event.text or ''

            if not text.strip():
                return

            if sender_id == my_id:
                return

            message_id = event.id

            logger.info(f"Incoming DM for tenant={tenant_id}: chat={chat_id}, sender={sender_id}")

            await _route_to_journey(tenant_id, chat_id, sender_id, text, message_id)
        except Exception as e:
            logger.exception(f"Error handling incoming message: {e}")

    _handlers[tenant_id] = _handle_incoming
    _listeners[tenant_id] = True
    logger.info(f"Listener started for tenant={tenant_id}")


async def _route_to_journey(tenant_id: str, chat_id: int, sender_id: int, text: str, message_id: int):
    try:
        from domains.journeys import repo
        from domains.journeys.engine import JourneyEngine

        if not repo.check_message_dedupe(tenant_id, chat_id, message_id):
            logger.debug(f"Duplicate message {message_id} for chat={chat_id}, skipping")
            return

        lock = _get_user_lock(chat_id)
        async with lock:
            sessions = repo.get_sessions_by_chat_id(tenant_id, chat_id)

            if sessions:
                engine = JourneyEngine()

                for session in sessions:
                    status = session.get('status')

                    if not session.get('current_step_id'):
                        repo.mark_session_broken(session['id'], "No current_step_id")
                        continue

                    step = repo.get_step_by_id(session['current_step_id'])
                    if not step:
                        repo.mark_session_broken(session['id'], f"Step {session['current_step_id']} not found")
                        continue

                    if status == 'awaiting_reply':
                        timeout_days = repo.get_journey_timeout_days(session['journey_id'])
                        last_activity = session.get('last_activity_at')
                        if last_activity:
                            try:
                                if isinstance(last_activity, str):
                                    last_dt = datetime.fromisoformat(last_activity)
                                else:
                                    last_dt = last_activity
                                if datetime.utcnow() - last_dt > timedelta(days=timeout_days):
                                    repo.update_session_status(session['id'], 'completed')
                                    repo.cancel_pending_scheduled_messages(session['id'])
                                    logger.info(f"Auto-completed inactive session {session['id']} (inactive {timeout_days}+ days)")
                                    continue
                            except Exception as e:
                                logger.warning(f"Error parsing last_activity_at for session {session['id']}: {e}")

                        result = engine.handle_wait_for_reply_response(session, text)
                        if result:
                            return
                        else:
                            repo.mark_session_broken(session['id'], "handle_wait_for_reply_response returned False")
                            continue

                    elif status == 'active':
                        engine.handle_user_reply(session, text)
                        return

            journey = repo.get_active_journey_by_dm_trigger(tenant_id, text)
            if journey:
                logger.info(f"DM trigger matched journey '{journey['name']}' for sender={sender_id}")
                engine = JourneyEngine()
                engine.start_journey_for_user(tenant_id, journey, chat_id, sender_id)
                return

            logger.debug(f"No actionable sessions or DM triggers for chat={chat_id}")
    except Exception as e:
        logger.exception(f"Error routing message to journey: {e}")


def start_listener_sync(tenant_id: str):
    from integrations.telegram.user_client import _run_in_bg
    try:
        _run_in_bg(start_listener(tenant_id))
    except Exception as e:
        logger.exception(f"Failed to start listener for tenant={tenant_id}: {e}")


async def _stop_listener_async(tenant_id: str):
    handler = _handlers.pop(tenant_id, None)
    if handler:
        from integrations.telegram.user_client import get_client
        client = get_client(tenant_id)
        if client.raw_client:
            client.raw_client.remove_event_handler(handler)
    _listeners.pop(tenant_id, None)
    logger.info(f"Listener stopped for tenant={tenant_id}")


def stop_listener(tenant_id: str):
    from integrations.telegram.user_client import _run_in_bg
    try:
        _run_in_bg(_stop_listener_async(tenant_id))
    except Exception:
        _handlers.pop(tenant_id, None)
        _listeners.pop(tenant_id, None)
        logger.info(f"Listener stopped (cleanup) for tenant={tenant_id}")
