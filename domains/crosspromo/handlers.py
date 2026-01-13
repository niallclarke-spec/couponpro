"""
Cross Promo HTTP Handlers - Thin handlers that delegate to service/repo.
"""
import json
from core.logging import get_logger
from domains.crosspromo import repo, service

logger = get_logger(__name__)


def _send_no_tenant_context(handler):
    """Send 403 when tenant context is missing."""
    handler.send_response(403)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'error': 'No tenant context available'}).encode())


def _send_json(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _read_json_body(handler) -> dict:
    """Read and parse JSON body from request."""
    content_length = int(handler.headers.get('Content-Length', 0))
    if content_length == 0:
        return {}
    body = handler.rfile.read(content_length)
    return json.loads(body.decode('utf-8'))


def handle_get_settings(handler):
    """GET /api/crosspromo/settings - Get cross promo settings for tenant."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    settings = repo.get_settings(tenant_id)
    
    if not settings:
        _send_json(handler, 200, {
            "tenant_id": tenant_id,
            "enabled": False,
            "bot_role": "signal_bot",
            "vip_channel_id": None,
            "free_channel_id": None,
            "cta_url": "https://entrylab.io/subscribe",
            "morning_post_time_utc": "07:00",
            "vip_soon_delay_minutes": 45,
            "timezone": "UTC"
        })
        return
    
    _send_json(handler, 200, settings)


def handle_save_settings(handler):
    """POST /api/crosspromo/settings - Create/update cross promo settings."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    data = _read_json_body(handler)
    
    result = repo.upsert_settings(
        tenant_id=tenant_id,
        enabled=data.get('enabled', False),
        bot_role=data.get('bot_role', 'signal_bot'),
        vip_channel_id=data.get('vip_channel_id'),
        free_channel_id=data.get('free_channel_id'),
        cta_url=data.get('cta_url', 'https://entrylab.io/subscribe'),
        morning_post_time_utc=data.get('morning_post_time_utc', '07:00'),
        vip_soon_delay_minutes=data.get('vip_soon_delay_minutes', 45),
        timezone=data.get('timezone', 'UTC')
    )
    
    if not result:
        _send_json(handler, 500, {"error": "Failed to save settings"})
        return
    
    _send_json(handler, 200, result)


def handle_list_jobs(handler):
    """GET /api/crosspromo/jobs - List cross promo jobs for tenant."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    jobs = repo.list_jobs(tenant_id, limit=50)
    _send_json(handler, 200, {"jobs": jobs})


def handle_run_daily_sequence(handler):
    """POST /api/crosspromo/run-daily-seq - Enqueue today's daily sequence."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    result = service.enqueue_daily_sequence(tenant_id)
    
    if not result.get('success'):
        error = result.get('error', 'Unknown error')
        if 'Monday-Friday' in error:
            _send_json(handler, 400, {"error": error})
        elif 'disabled' in error:
            _send_json(handler, 409, {"error": error})
        elif 'not configured' in error:
            _send_json(handler, 503, {"error": error})
        else:
            _send_json(handler, 400, {"error": error})
        return
    
    _send_json(handler, 200, result)


def handle_publish_win(handler):
    """POST /api/crosspromo/publish-win - Enqueue win promo sequence."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    data = _read_json_body(handler)
    
    vip_signal_message_id = data.get('vip_signal_message_id')
    vip_win_message_id = data.get('vip_win_message_id')
    
    if not vip_signal_message_id or not vip_win_message_id:
        _send_json(handler, 400, {"error": "Missing vip_signal_message_id or vip_win_message_id"})
        return
    
    try:
        vip_signal_message_id = int(vip_signal_message_id)
        vip_win_message_id = int(vip_win_message_id)
    except (ValueError, TypeError):
        _send_json(handler, 400, {"error": "Message IDs must be integers"})
        return
    
    result = service.enqueue_win_sequence(tenant_id, vip_signal_message_id, vip_win_message_id)
    
    if not result.get('success'):
        error = result.get('error', 'Unknown error')
        if 'Monday-Friday' in error:
            _send_json(handler, 400, {"error": error})
        elif 'disabled' in error:
            _send_json(handler, 409, {"error": error})
        elif 'not configured' in error:
            _send_json(handler, 503, {"error": error})
        else:
            _send_json(handler, 400, {"error": error})
        return
    
    _send_json(handler, 200, result)


def handle_send_test(handler):
    """POST /api/crosspromo/send-test - Send test morning message."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    result = service.send_test_morning_message(tenant_id)
    
    if not result.get('success'):
        error = result.get('error', 'Unknown error')
        if 'not configured' in error.lower():
            _send_json(handler, 503, {"error": error})
        else:
            _send_json(handler, 400, {"error": error})
        return
    
    _send_json(handler, 200, {"success": True, "message": "Test message sent"})


def handle_get_preview(handler):
    """GET /api/crosspromo/preview - Get morning message preview."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    preview = service.get_morning_preview(tenant_id)
    _send_json(handler, 200, {"preview": preview})


def handle_test_cta(handler):
    """POST /api/crosspromo/test-cta - Send test CTA with optional sticker to free channel."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    result = service.send_test_cta(tenant_id)
    
    if not result.get('success'):
        error = result.get('error', 'Unknown error')
        if 'not configured' in error.lower():
            _send_json(handler, 503, {"error": error})
        else:
            _send_json(handler, 400, {"error": error})
        return
    
    _send_json(handler, 200, {"success": True, "message": "Test CTA sent to free channel"})


def handle_test_forward_promo(handler):
    """POST /api/crosspromo/test-forward-promo - Send test AI promo message to free channel."""
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    
    result = service.send_test_forward_promo(tenant_id, pips_secured=179.0)
    
    if not result.get('success'):
        error = result.get('error', 'Unknown error')
        if 'not configured' in error.lower():
            _send_json(handler, 503, {"error": error})
        else:
            _send_json(handler, 400, {"error": error})
        return
    
    _send_json(handler, 200, {
        "success": True, 
        "message": "Test promo message sent to free channel",
        "content": result.get('message_sent')
    })
