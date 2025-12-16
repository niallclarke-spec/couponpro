"""
Telegram webhook HTTP handlers.

Extracted from server.py - these handle incoming Telegram webhook POST requests.
Handlers receive dependencies as parameters to avoid stale module globals.
"""
import json
import sys
import time

from core.config import Config
from core.logging import get_logger

logger = get_logger(__name__)


def check_journey_trigger(webhook_data: dict, tenant_id: str, bot_id: str) -> bool:
    """
    Check if this webhook update should trigger a journey.
    
    Returns True if a journey was started (and we should skip normal processing),
    Returns False if no journey matched (continue normal processing).
    """
    try:
        message = webhook_data.get('message', {})
        text = message.get('text', '')
        
        if not text or not text.startswith('/start '):
            return False
        
        from domains.journeys.triggers import parse_telegram_deeplink
        start_param = parse_telegram_deeplink(text)
        
        if not start_param:
            return False
        
        chat_id = message.get('chat', {}).get('id')
        user_id = message.get('from', {}).get('id')
        
        if not chat_id or not user_id:
            logger.warning("Missing chat_id or user_id in webhook message")
            return False
        
        from domains.journeys import repo
        journey = repo.get_active_journey_by_deeplink(tenant_id, bot_id, start_param)
        
        if not journey:
            logger.debug(f"No active journey found for deeplink param: {start_param}")
            return False
        
        logger.info(f"Found journey '{journey['name']}' for deeplink param: {start_param}")
        
        from domains.journeys.engine import JourneyEngine
        
        def send_message_fn(chat_id: int, text: str, bot_id: str) -> bool:
            try:
                import requests
                from core.config import Config
                bot_token = Config.get_telegram_bot_token()
                if not bot_token:
                    logger.error("No bot token available for journey message")
                    return False
                
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
                logger.exception(f"Error sending journey message: {e}")
                return False
        
        engine = JourneyEngine(send_message_fn=send_message_fn)
        session = engine.start_journey_for_user(
            tenant_id=tenant_id,
            journey=journey,
            telegram_chat_id=chat_id,
            telegram_user_id=user_id
        )
        
        if session:
            logger.info(f"Started journey session {session['id']} for user {user_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.exception(f"Error checking journey trigger: {e}")
        return False


def check_journey_reply(webhook_data: dict, tenant_id: str, bot_id: str) -> bool:
    """
    Check if this webhook update is a reply to an active journey question.
    
    Returns True if we handled the reply (skip normal processing),
    Returns False otherwise.
    """
    try:
        message = webhook_data.get('message', {})
        text = message.get('text', '')
        
        if not text:
            return False
        
        if text.startswith('/'):
            return False
        
        chat_id = message.get('chat', {}).get('id')
        user_id = message.get('from', {}).get('id')
        
        if not chat_id or not user_id:
            return False
        
        from domains.journeys import repo
        session = repo.get_session_for_user_reply(tenant_id, user_id, chat_id)
        
        if not session:
            return False
        
        if session['status'] != 'active':
            return False
        
        current_step = repo.get_step_by_id(session['current_step_id']) if session['current_step_id'] else None
        
        if not current_step or current_step['step_type'] != 'question':
            return False
        
        logger.info(f"Processing journey reply for session {session['id']}")
        
        from domains.journeys.engine import JourneyEngine
        
        def send_message_fn(chat_id: int, text: str, bot_id: str) -> bool:
            try:
                import requests
                from core.config import Config
                bot_token = Config.get_telegram_bot_token()
                if not bot_token:
                    return False
                
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                response = requests.post(url, json={
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'HTML'
                }, timeout=10)
                return response.status_code == 200
            except Exception:
                return False
        
        engine = JourneyEngine(send_message_fn=send_message_fn)
        result = engine.handle_user_reply(session, text, bot_id)
        
        return result
        
    except Exception as e:
        logger.exception(f"Error checking journey reply: {e}")
        return False


def handle_coupon_telegram_webhook(handler, telegram_bot_available, telegram_bot_module):
    """POST /api/telegram-webhook - Coupon bot webhook handler"""
    start_time = time.time()
    print(f"[WEBHOOK-ENDPOINT] ⚡ Webhook endpoint called!", flush=True)
    sys.stdout.flush()
    
    if not telegram_bot_available:
        print(f"[WEBHOOK-ENDPOINT] ❌ Bot not available", flush=True)
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Telegram bot not available'}).encode())
        return
    
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        post_data = handler.rfile.read(content_length)
        print(f"[WEBHOOK-ENDPOINT] Received {content_length} bytes", flush=True)
        bot_token = Config.get_telegram_bot_token()
        
        if not bot_token:
            print(f"[WEBHOOK-ENDPOINT] ❌ Bot token not configured", flush=True)
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Bot token not configured'}).encode())
            return
        
        # Parse JSON from webhook
        webhook_data = json.loads(post_data.decode('utf-8'))
        update_id = webhook_data.get('update_id', 'unknown')
        print(f"[WEBHOOK-ENDPOINT] Processing update_id: {update_id}", flush=True)
        
        # Check for journey triggers first (hardcoded to entrylab for now)
        # TODO: In future, determine tenant_id from bot token mapping
        tenant_id = 'entrylab'
        bot_id = 'default'
        
        if check_journey_trigger(webhook_data, tenant_id, bot_id):
            print(f"[WEBHOOK-ENDPOINT] ✅ Handled by journey trigger", flush=True)
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'status': 'ok', 'handler': 'journey'}).encode())
            return
        
        # Check for journey reply (user answering a question)
        if check_journey_reply(webhook_data, tenant_id, bot_id):
            print(f"[WEBHOOK-ENDPOINT] ✅ Handled by journey reply", flush=True)
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'status': 'ok', 'handler': 'journey_reply'}).encode())
            return
        
        # Handle the webhook (tracking happens inside bot handlers)
        result = telegram_bot_module.handle_telegram_webhook(webhook_data, bot_token)
        
        elapsed = time.time() - start_time
        print(f"[WEBHOOK-ENDPOINT] ✅ Completed update_id {update_id} in {elapsed:.2f}s, result: {result}", flush=True)
        sys.stdout.flush()
        
        # Telegram expects 200 OK even if we couldn't process the command
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[WEBHOOK-ENDPOINT] ❌ Webhook error after {elapsed:.2f}s: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        # Still send 200 to Telegram so it doesn't retry
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_forex_telegram_webhook(handler, telegram_bot_available, telegram_bot_module):
    """POST /api/forex-telegram-webhook - Forex bot webhook handler"""
    start_time = time.time()
    print(f"[FOREX-WEBHOOK] ⚡ Forex webhook endpoint called!", flush=True)
    sys.stdout.flush()
    
    if not telegram_bot_available:
        print(f"[FOREX-WEBHOOK] ❌ Telegram bot module not available", flush=True)
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Telegram bot not available'}).encode())
        return
    
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        post_data = handler.rfile.read(content_length)
        
        # Use appropriate bot token based on environment
        from forex_bot import get_forex_bot_token
        forex_bot_token = get_forex_bot_token()
        
        if not forex_bot_token:
            print(f"[FOREX-WEBHOOK] ❌ Forex bot token not configured", flush=True)
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Forex bot token not configured'}).encode())
            return
        
        webhook_data = json.loads(post_data.decode('utf-8'))
        update_id = webhook_data.get('update_id', 'unknown')
        print(f"[FOREX-WEBHOOK] Processing update_id: {update_id}", flush=True)
        
        result = telegram_bot_module.handle_forex_webhook(webhook_data, forex_bot_token)
        
        elapsed = time.time() - start_time
        print(f"[FOREX-WEBHOOK] ✅ Completed update_id {update_id} in {elapsed:.2f}s, result: {result}", flush=True)
        sys.stdout.flush()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[FOREX-WEBHOOK] ❌ Webhook error after {elapsed:.2f}s: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
