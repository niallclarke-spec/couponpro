"""
Onboarding domain handlers.

Handles onboarding API endpoints for tenant setup including:
- Telegram bot token verification
- Stripe keys verification  
- Business info configuration
"""
import json
import urllib.request
import urllib.error

from auth.clerk_auth import get_auth_user_from_request
import db

from core.logging import get_logger
logger = get_logger(__name__)


def _send_json_response(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _get_tenant_id_from_handler(handler) -> str:
    """Extract tenant_id from handler (set by middleware)."""
    return getattr(handler, 'tenant_id', None)


def _require_tenant_id(handler) -> str:
    """Require tenant_id or send 401 error. Returns tenant_id or None if error sent."""
    tenant_id = _get_tenant_id_from_handler(handler)
    if not tenant_id:
        auth_user = get_auth_user_from_request(handler)
        if not auth_user:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return None
        user_row = db.get_user_by_clerk_id(auth_user['clerk_user_id'])
        if not user_row or not user_row.get('tenant_id'):
            _send_json_response(handler, 401, {'error': 'User not associated with a tenant'})
            return None
        tenant_id = user_row['tenant_id']
    return tenant_id


def handle_onboarding_state(handler):
    """GET /api/onboarding/state - Returns current onboarding state for authenticated tenant."""
    try:
        tenant_id = _require_tenant_id(handler)
        if not tenant_id:
            return
        
        state = db.get_onboarding_state(tenant_id)
        
        if not state:
            state = db.create_onboarding_state(tenant_id)
        
        if state:
            _send_json_response(handler, 200, {'success': True, 'state': state})
        else:
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to get onboarding state'})
    except Exception as e:
        logger.exception("Error getting onboarding state")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})


def handle_onboarding_telegram(handler):
    """POST /api/onboarding/telegram - Verify and save Telegram bot token."""
    try:
        tenant_id = _require_tenant_id(handler)
        if not tenant_id:
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json_response(handler, 400, {'success': False, 'error': 'Request body required'})
            return
        
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        bot_token = data.get('bot_token', '').strip()
        
        if not bot_token:
            _send_json_response(handler, 400, {'success': False, 'error': 'bot_token is required'})
            return
        
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            req = urllib.request.Request(url, method='GET')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                bot_info = json.loads(response.read().decode('utf-8'))
            
            if not bot_info.get('ok'):
                _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Telegram bot token'})
                return
            
            bot_result = bot_info.get('result', {})
            bot_username = bot_result.get('username', '')
            bot_name = bot_result.get('first_name', '')
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ''
            logger.warning(f"Telegram API error: {e.code} - {error_body}")
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Telegram bot token'})
            return
        except Exception as e:
            logger.exception("Error verifying Telegram token")
            _send_json_response(handler, 400, {'success': False, 'error': f'Failed to verify token: {str(e)}'})
            return
        
        integration_config = {
            'bot_token': bot_token,
            'bot_username': bot_username,
            'bot_name': bot_name,
            'verified_at': db.datetime.now().isoformat()
        }
        
        if not db.save_tenant_integration(tenant_id, 'telegram', integration_config):
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to save integration'})
            return
        
        step_data = {
            'bot_username': bot_username,
            'bot_name': bot_name,
            'verified': True
        }
        state = db.update_onboarding_step(tenant_id, 'telegram', step_data)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state,
                'bot_info': {
                    'username': bot_username,
                    'name': bot_name
                }
            })
        else:
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to update onboarding state'})
            
    except json.JSONDecodeError:
        _send_json_response(handler, 400, {'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        logger.exception("Error in telegram onboarding")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})


def handle_onboarding_stripe(handler):
    """POST /api/onboarding/stripe - Verify and save Stripe keys."""
    try:
        tenant_id = _require_tenant_id(handler)
        if not tenant_id:
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json_response(handler, 400, {'success': False, 'error': 'Request body required'})
            return
        
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        secret_key = data.get('secret_key', '').strip()
        publishable_key = data.get('publishable_key', '').strip()
        
        if not secret_key:
            _send_json_response(handler, 400, {'success': False, 'error': 'secret_key is required'})
            return
        
        if not secret_key.startswith('sk_'):
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Stripe secret key format'})
            return
        
        if publishable_key and not publishable_key.startswith('pk_'):
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Stripe publishable key format'})
            return
        
        try:
            import base64
            url = "https://api.stripe.com/v1/balance"
            req = urllib.request.Request(url, method='GET')
            
            auth_string = f"{secret_key}:"
            auth_bytes = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
            req.add_header('Authorization', f'Basic {auth_bytes}')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                balance_info = json.loads(response.read().decode('utf-8'))
            
            is_live = not secret_key.startswith('sk_test_')
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ''
            logger.warning(f"Stripe API error: {e.code} - {error_body}")
            if e.code == 401:
                _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Stripe API key'})
            else:
                _send_json_response(handler, 400, {'success': False, 'error': f'Stripe verification failed: {e.code}'})
            return
        except Exception as e:
            logger.exception("Error verifying Stripe keys")
            _send_json_response(handler, 400, {'success': False, 'error': f'Failed to verify keys: {str(e)}'})
            return
        
        integration_config = {
            'secret_key': secret_key,
            'publishable_key': publishable_key or '',
            'is_live': is_live,
            'verified_at': db.datetime.now().isoformat()
        }
        
        if not db.save_tenant_integration(tenant_id, 'stripe', integration_config):
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to save integration'})
            return
        
        step_data = {
            'is_live': is_live,
            'verified': True
        }
        state = db.update_onboarding_step(tenant_id, 'stripe', step_data)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state,
                'stripe_info': {
                    'is_live': is_live,
                    'has_publishable_key': bool(publishable_key)
                }
            })
        else:
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to update onboarding state'})
            
    except json.JSONDecodeError:
        _send_json_response(handler, 400, {'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        logger.exception("Error in stripe onboarding")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})


def handle_onboarding_business(handler):
    """POST /api/onboarding/business - Save business info."""
    try:
        tenant_id = _require_tenant_id(handler)
        if not tenant_id:
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json_response(handler, 400, {'success': False, 'error': 'Request body required'})
            return
        
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        display_name = data.get('display_name', '').strip()
        support_email = data.get('support_email', '').strip()
        logo_url = data.get('logo_url', '').strip()
        
        if not display_name:
            _send_json_response(handler, 400, {'success': False, 'error': 'display_name is required'})
            return
        
        if not support_email:
            _send_json_response(handler, 400, {'success': False, 'error': 'support_email is required'})
            return
        
        if '@' not in support_email or '.' not in support_email:
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid support_email format'})
            return
        
        step_data = {
            'display_name': display_name,
            'support_email': support_email,
            'logo_url': logo_url or None,
            'updated': True
        }
        state = db.update_onboarding_step(tenant_id, 'business', step_data)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state
            })
        else:
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to update onboarding state'})
            
    except json.JSONDecodeError:
        _send_json_response(handler, 400, {'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        logger.exception("Error in business onboarding")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})


def handle_onboarding_complete(handler):
    """POST /api/onboarding/complete - Mark onboarding as complete if all steps done."""
    try:
        tenant_id = _require_tenant_id(handler)
        if not tenant_id:
            return
        
        current_state = db.get_onboarding_state(tenant_id)
        
        if not current_state:
            _send_json_response(handler, 400, {'success': False, 'error': 'Onboarding not started'})
            return
        
        if not current_state.get('telegram_completed'):
            _send_json_response(handler, 400, {
                'success': False,
                'error': 'Telegram step not completed',
                'missing_step': 'telegram'
            })
            return
        
        if not current_state.get('stripe_completed'):
            _send_json_response(handler, 400, {
                'success': False,
                'error': 'Stripe step not completed',
                'missing_step': 'stripe'
            })
            return
        
        if not current_state.get('business_completed'):
            _send_json_response(handler, 400, {
                'success': False,
                'error': 'Business info step not completed',
                'missing_step': 'business'
            })
            return
        
        state = db.complete_onboarding(tenant_id)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state,
                'message': 'Onboarding completed successfully'
            })
        else:
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to complete onboarding'})
            
    except Exception as e:
        logger.exception("Error completing onboarding")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})
