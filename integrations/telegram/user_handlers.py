import json

from core.logging import get_logger

logger = get_logger('telethon_handlers')


def _send_json(handler, status_code, data):
    handler.send_response(status_code)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _read_json_body(handler):
    content_length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(content_length)
    return json.loads(body) if body else {}


def handle_telethon_status(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        import os
        from integrations.telegram.user_client import get_client
        client = get_client(tenant_id)
        auto_connect = os.environ.get('TELETHON_AUTO_CONNECT', 'true').lower() != 'false'
        if not auto_connect and not client.is_connected():
            client.status = 'disconnected'
            client.last_error = None
            _send_json(handler, 200, {
                'tenant_id': client.tenant_id,
                'status': 'disconnected',
                'connected': False,
                'auto_connect_disabled': True,
                'last_heartbeat': None,
                'last_send': None,
                'last_error': None,
                'sends_today': 0,
                'has_credentials': False,
                'has_api_id': False,
                'masked_phone': None,
                'has_session_file': False,
            })
            return
        status = client.get_status()
        if auto_connect and status.get('has_session_file') and status.get('has_credentials') and not status.get('connected') and status.get('status') != 'error':
            try:
                ok = client.connect_sync()
                if ok:
                    from integrations.telegram.user_listener import start_listener_sync
                    start_listener_sync(tenant_id)
                    status = client.get_status()
            except Exception as ce:
                logger.warning(f"Auto-connect on status check failed: {ce}")
        _send_json(handler, 200, status)
    except Exception as e:
        logger.exception(f"Error getting telethon status: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_send_code(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        data = _read_json_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return

    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    phone = data.get('phone')

    if not api_id or not api_hash or not phone:
        _send_json(handler, 400, {'error': 'api_id, api_hash, and phone are required'})
        return

    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        _send_json(handler, 400, {'error': 'api_id must be a number'})
        return

    try:
        from integrations.telegram.user_auth import send_verification_code
        result = send_verification_code(tenant_id, api_id, api_hash, phone)
        status_code = 200 if result.get('success') else 400
        _send_json(handler, status_code, result)
    except Exception as e:
        logger.exception(f"Error sending verification code: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_verify_code(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        data = _read_json_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return

    code = data.get('code')
    phone_code_hash = data.get('phone_code_hash')

    if not code or not phone_code_hash:
        _send_json(handler, 400, {'error': 'code and phone_code_hash are required'})
        return

    try:
        from integrations.telegram.user_auth import verify_code
        result = verify_code(tenant_id, str(code), phone_code_hash)
        status_code = 200 if result.get('success') else 400
        _send_json(handler, status_code, result)
    except Exception as e:
        logger.exception(f"Error verifying code: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_verify_2fa(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        data = _read_json_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return

    password = data.get('password')
    if not password:
        _send_json(handler, 400, {'error': 'password is required'})
        return

    try:
        from integrations.telegram.user_auth import verify_2fa
        result = verify_2fa(tenant_id, password)
        status_code = 200 if result.get('success') else 400
        _send_json(handler, status_code, result)
    except Exception as e:
        logger.exception(f"Error verifying 2FA: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_reconnect(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        from integrations.telegram.user_client import get_client
        client = get_client(tenant_id)
        success = client.reconnect_sync()
        if success:
            from integrations.telegram.user_listener import start_listener_sync
            start_listener_sync(tenant_id)
        _send_json(handler, 200, {
            'success': success,
            'status': client.get_status(),
        })
    except Exception as e:
        logger.exception(f"Error reconnecting telethon: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_disconnect(handler):
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        from integrations.telegram.user_client import get_client
        client = get_client(tenant_id)
        client.disconnect_sync()
        _send_json(handler, 200, {
            'success': True,
            'status': client.get_status(),
        })
    except Exception as e:
        logger.exception(f"Error disconnecting telethon: {e}")
        _send_json(handler, 500, {'error': str(e)})


def handle_telethon_save_credentials(handler):
    """POST /api/telethon/credentials - Save Telethon credentials to DB."""
    tenant_id = getattr(handler, 'tenant_id', 'entrylab')
    try:
        data = _read_json_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return

    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    phone = data.get('phone')

    if not api_id or not api_hash or not phone:
        _send_json(handler, 400, {'error': 'api_id, api_hash, and phone are required'})
        return

    try:
        api_id = int(api_id)
    except (ValueError, TypeError):
        _send_json(handler, 400, {'error': 'api_id must be a number'})
        return

    try:
        from domains.connections.repo import save_telethon_credentials
        success = save_telethon_credentials(tenant_id, api_id, api_hash, phone)
        if success:
            from integrations.telegram.user_client import get_client
            client = get_client(tenant_id)
            client.reload_credentials()
            logger.info(f"Telethon credentials saved for tenant={tenant_id}")
            _send_json(handler, 200, {'success': True, 'status': client.get_status()})
        else:
            _send_json(handler, 500, {'error': 'Failed to save credentials'})
    except Exception as e:
        logger.exception(f"Error saving telethon credentials: {e}")
        _send_json(handler, 500, {'error': str(e)})
