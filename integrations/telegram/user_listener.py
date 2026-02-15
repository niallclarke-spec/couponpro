"""
Telethon inbound message listener for Journeys.

Listens for incoming messages on the user client and routes them
to active journey sessions for processing replies.
"""
import asyncio
from typing import Optional, Dict, Callable
from telethon import events
from core.logging import get_logger

logger = get_logger('telethon_listener')

_listeners: Dict[str, bool] = {}
_handlers: Dict[str, Callable] = {}


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

    me = await tc.get_me()
    my_id = me.id

    @tc.on(events.NewMessage(incoming=True))
    async def _handle_incoming(event):
        try:
            chat_id = event.chat_id
            sender_id = event.sender_id
            text = event.text or ''

            if not text.strip():
                return

            if sender_id == my_id:
                return

            logger.info(f"Incoming message for tenant={tenant_id}: chat={chat_id}, sender={sender_id}")

            _route_to_journey(tenant_id, chat_id, sender_id, text)
        except Exception as e:
            logger.exception(f"Error handling incoming message: {e}")

    _handlers[tenant_id] = _handle_incoming
    _listeners[tenant_id] = True
    logger.info(f"Listener started for tenant={tenant_id}")


def _route_to_journey(tenant_id: str, chat_id: int, sender_id: int, text: str):
    try:
        from domains.journeys import repo
        from domains.journeys.engine import JourneyEngine

        sessions = repo.get_sessions_by_chat_id(tenant_id, chat_id)

        if not sessions:
            logger.debug(f"No active journey sessions for chat={chat_id}")
            return

        engine = JourneyEngine()

        for session in sessions:
            status = session.get('status')

            if status == 'awaiting_reply':
                logger.info(f"Routing reply to wait_for_reply session {session['id']}")
                engine.handle_wait_for_reply_response(session, text)
                return

            elif status == 'active':
                logger.info(f"Routing reply to question session {session['id']}")
                engine.handle_user_reply(session, text)
                return

        logger.debug(f"No actionable sessions for chat={chat_id}")
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
