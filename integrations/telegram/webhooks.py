"""
Telegram webhook HTTP handlers.

Extracted from server.py - these handle incoming Telegram webhook POST requests.
Handlers receive dependencies as parameters to avoid stale module globals.
"""
import json
import sys
import time

from core.config import Config


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
