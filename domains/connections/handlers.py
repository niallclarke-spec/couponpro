"""
Connections domain handlers - manages tenant bot configurations.
"""
import json
import os
import secrets
import requests

import asyncio
import db
from core.logging import get_logger
from core.bot_credentials import SIGNAL_BOT, MESSAGE_BOT, VALID_BOT_ROLES
from core.telegram_sender import invalidate_connection_cache, validate_bot_credentials

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def _send_json(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _get_host(handler) -> str:
    """Get host for webhook URL from DOMAIN env var or Host header."""
    domain = os.environ.get('DOMAIN')
    if domain:
        return domain
    return handler.headers.get('Host', 'localhost')


def _validate_telegram_token(bot_token: str) -> tuple:
    """
    Validate a Telegram bot token by calling getMe API.
    
    Returns:
        (success: bool, bot_username: str or None, error: str or None)
    """
    try:
        url = f"{TELEGRAM_API_BASE}{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get('ok') and data.get('result'):
            username = data['result'].get('username', '')
            return True, f"@{username}" if username else None, None
        else:
            error = data.get('description', 'Invalid bot token')
            return False, None, error
    except requests.RequestException as e:
        logger.exception(f"Error validating Telegram token: {e}")
        return False, None, str(e)


def handle_connections_list(handler):
    """GET /api/connections - List all bot connections for tenant."""
    try:
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
        if not db.db_pool or not db.db_pool.connection_pool:
            _send_json(handler, 503, {'error': 'Database not available'})
            return
        
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT bot_role, bot_username, webhook_url, channel_id, last_validated_at, last_error,
                       vip_channel_id, free_channel_id
                FROM tenant_bot_connections
                WHERE tenant_id = %s
                ORDER BY bot_role
            """, (tenant_id,))
            
            rows = cursor.fetchall()
            connections = []
            for row in rows:
                connections.append({
                    'bot_role': row[0],
                    'bot_username': row[1],
                    'webhook_url': row[2],
                    'channel_id': row[3],
                    'last_validated_at': row[4].isoformat() if row[4] else None,
                    'last_error': row[5],
                    'vip_channel_id': row[6],
                    'free_channel_id': row[7]
                })
        
        _send_json(handler, 200, {'connections': connections})
        
    except Exception as e:
        logger.exception(f"Error listing connections: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_connection_validate(handler):
    """POST /api/connections/validate - Validate a bot token without saving."""
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return
    
    bot_role = data.get('bot_role')
    bot_token = data.get('bot_token')
    
    if bot_role not in VALID_BOT_ROLES:
        _send_json(handler, 400, {'error': f'bot_role must be "{SIGNAL_BOT}" or "{MESSAGE_BOT}"'})
        return
    
    if not bot_token:
        _send_json(handler, 400, {'error': 'bot_token is required'})
        return
    
    valid, bot_username, error = _validate_telegram_token(bot_token)
    
    if valid:
        _send_json(handler, 200, {'valid': True, 'bot_username': bot_username})
    else:
        _send_json(handler, 200, {'valid': False, 'error': error})


def handle_connection_test(handler):
    """POST /api/connections/test - Test an existing or new connection."""
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return
    
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    bot_role = data.get('bot_role')
    bot_token = data.get('bot_token')
    
    if bot_role not in VALID_BOT_ROLES:
        _send_json(handler, 400, {'error': f'bot_role must be "{SIGNAL_BOT}" or "{MESSAGE_BOT}"'})
        return
    
    if not bot_token:
        connection = db.get_bot_connection(tenant_id, bot_role)
        if connection and connection.get('bot_token'):
            bot_token = connection['bot_token']
        else:
            _send_json(handler, 400, {'error': 'No token provided and no saved connection found'})
            return
    
    valid, bot_username, error = _validate_telegram_token(bot_token)
    
    if valid:
        _send_json(handler, 200, {'success': True, 'bot_username': bot_username})
    else:
        _send_json(handler, 200, {'success': False, 'error': error})


def handle_connection_save(handler):
    """POST /api/connections - Validate token, set webhook, and save connection."""
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return
    
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    bot_role = data.get('bot_role')
    bot_token = data.get('bot_token')
    channel_id = data.get('channel_id')
    vip_channel_id = data.get('vip_channel_id')
    free_channel_id = data.get('free_channel_id')
    
    if bot_role not in VALID_BOT_ROLES:
        _send_json(handler, 400, {'error': f'bot_role must be "{SIGNAL_BOT}" or "{MESSAGE_BOT}"'})
        return
    
    if not bot_token:
        _send_json(handler, 400, {'error': 'bot_token is required'})
        return
    
    valid, bot_username, error = _validate_telegram_token(bot_token)
    if not valid:
        _send_json(handler, 400, {'error': f'Invalid bot token: {error}'})
        return
    
    webhook_secret = secrets.token_urlsafe(32)
    host = _get_host(handler)
    webhook_url = f"https://{host}/api/bot-webhook/{webhook_secret}"
    
    try:
        set_webhook_url = f"{TELEGRAM_API_BASE}{bot_token}/setWebhook"
        response = requests.post(set_webhook_url, json={'url': webhook_url}, timeout=10)
        webhook_data = response.json()
        
        if not webhook_data.get('ok'):
            error_msg = webhook_data.get('description', 'Failed to set webhook')
            _send_json(handler, 400, {'error': f'Failed to set webhook: {error_msg}'})
            return
    except requests.RequestException as e:
        logger.exception(f"Error setting webhook: {e}")
        _send_json(handler, 500, {'error': f'Failed to set webhook: {e}'})
        return
    
    success = db.upsert_bot_connection(
        tenant_id=tenant_id,
        bot_role=bot_role,
        bot_token=bot_token,
        bot_username=bot_username,
        webhook_secret=webhook_secret,
        webhook_url=webhook_url,
        channel_id=channel_id,
        vip_channel_id=vip_channel_id,
        free_channel_id=free_channel_id
    )
    
    if success:
        invalidate_connection_cache(tenant_id, bot_role)
        logger.info(
            f"Saved bot connection: tenant={tenant_id}, role={bot_role}, "
            f"username={bot_username}, vip_channel={vip_channel_id}, free_channel={free_channel_id}"
        )
        from datetime import datetime
        _send_json(handler, 200, {
            'success': True,
            'connection': {
                'bot_role': bot_role,
                'bot_username': bot_username,
                'webhook_url': webhook_url,
                'channel_id': channel_id,
                'vip_channel_id': vip_channel_id,
                'free_channel_id': free_channel_id,
                'updated_at': datetime.utcnow().isoformat() + 'Z'
            }
        })
    else:
        _send_json(handler, 500, {'error': 'Failed to save connection to database'})


def handle_connection_delete(handler, bot_role: str):
    """DELETE /api/connections/:bot_role - Remove webhook and delete connection."""
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    
    if bot_role not in VALID_BOT_ROLES:
        _send_json(handler, 400, {'error': f'bot_role must be "{SIGNAL_BOT}" or "{MESSAGE_BOT}"'})
        return
    
    if not db.db_pool or not db.db_pool.connection_pool:
        _send_json(handler, 503, {'error': 'Database not available'})
        return
    
    try:
        connection = db.get_bot_connection(tenant_id, bot_role)
        if not connection:
            _send_json(handler, 404, {'error': 'Connection not found'})
            return
        
        bot_token = connection.get('bot_token')
        if bot_token:
            try:
                delete_webhook_url = f"{TELEGRAM_API_BASE}{bot_token}/deleteWebhook"
                response = requests.post(delete_webhook_url, timeout=10)
                webhook_data = response.json()
                if not webhook_data.get('ok'):
                    logger.warning(f"Failed to delete webhook: {webhook_data.get('description')}")
            except requests.RequestException as e:
                logger.warning(f"Error deleting webhook: {e}")
        
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM tenant_bot_connections
                WHERE tenant_id = %s AND bot_role = %s
            """, (tenant_id, bot_role))
            conn.commit()
        
        invalidate_connection_cache(tenant_id, bot_role)
        logger.info(f"Deleted bot connection: tenant={tenant_id}, role={bot_role}")
        _send_json(handler, 200, {'success': True})
        
    except Exception as e:
        logger.exception(f"Error deleting connection: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_connection_validate_saved(handler):
    """POST /api/connections/validate-saved - Validate a saved bot connection using Telegram API.
    
    This is a dry-run validation that:
    1. Fetches credentials from DB (fresh, not cached)
    2. Calls Telegram getMe() to validate the token
    3. Calls Telegram getChat() to validate channel access
    
    Returns JSON with validation results:
    {
        'ok': bool,
        'bot_username': str or None,
        'bot_id': int or None,
        'channel_valid': bool or None,
        'channel_title': str or None,
        'error': str or None
    }
    """
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return
    
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    bot_role = data.get('bot_role')
    
    if bot_role not in VALID_BOT_ROLES:
        _send_json(handler, 400, {'error': f'bot_role must be "{SIGNAL_BOT}" or "{MESSAGE_BOT}"'})
        return
    
    try:
        result = asyncio.get_event_loop().run_until_complete(
            validate_bot_credentials(tenant_id, bot_role)
        )
        _send_json(handler, 200, result)
        
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                validate_bot_credentials(tenant_id, bot_role)
            )
            _send_json(handler, 200, result)
        finally:
            loop.close()
    except Exception as e:
        logger.exception(f"Error validating connection: {e}")
        _send_json(handler, 500, {'error': str(e)})
