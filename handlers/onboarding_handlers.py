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
import urllib.parse
from datetime import datetime

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


def _require_tenant_id_or_create(handler) -> str:
    """
    Get tenant_id from handler, or create one for new users during onboarding.
    
    For new users without a tenant mapping, auto-provisions a tenant using
    bootstrap_tenant (random UUID for uniqueness) and creates initial onboarding state.
    
    Returns tenant_id or None if authentication fails.
    """
    tenant_id = _get_tenant_id_from_handler(handler)
    if tenant_id:
        return tenant_id
    
    clerk_user_id = getattr(handler, 'clerk_user_id', None)
    clerk_email = getattr(handler, 'clerk_email', None) or handler.headers.get('X-Clerk-User-Email', '')
    
    if not clerk_user_id:
        auth_user = get_auth_user_from_request(handler)
        if not auth_user:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return None
        clerk_user_id = auth_user['clerk_user_id']
        clerk_email = auth_user.get('email') or clerk_email
    
    from core.tenant_credentials import get_tenant_for_user, bootstrap_tenant
    
    existing_tenant = get_tenant_for_user(clerk_user_id)
    if existing_tenant:
        db.create_onboarding_state(existing_tenant)
        return existing_tenant
    
    tenant_id = bootstrap_tenant(clerk_user_id, clerk_email)
    if not tenant_id:
        _send_json_response(handler, 500, {'error': 'Failed to create tenant'})
        return None
    
    db.create_onboarding_state(tenant_id)
    
    return tenant_id


def handle_onboarding_state(handler):
    """GET /api/onboarding/state - Returns current onboarding state for authenticated tenant."""
    try:
        tenant_id = _require_tenant_id_or_create(handler)
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
    """POST /api/onboarding/telegram - Verify and save Telegram bot token and channel IDs."""
    try:
        tenant_id = _require_tenant_id_or_create(handler)
        if not tenant_id:
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json_response(handler, 400, {'success': False, 'error': 'Request body required'})
            return
        
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        bot_token = data.get('bot_token', '').strip()
        free_channel_id = data.get('free_channel_id', '').strip()
        vip_channel_id = data.get('vip_channel_id', '').strip()
        
        if not bot_token:
            _send_json_response(handler, 400, {'success': False, 'error': 'bot_token is required'})
            return
        
        if not free_channel_id:
            _send_json_response(handler, 400, {'success': False, 'error': 'free_channel_id is required'})
            return
        
        if not vip_channel_id:
            _send_json_response(handler, 400, {'success': False, 'error': 'vip_channel_id is required'})
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
        
        free_channel_verified = False
        vip_channel_verified = False
        free_channel_error = None
        vip_channel_error = None
        
        try:
            chat_id_param = free_channel_id if free_channel_id.startswith('-') else free_channel_id
            url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={urllib.parse.quote(chat_id_param, safe='@')}"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                chat_info = json.loads(response.read().decode('utf-8'))
                free_channel_verified = chat_info.get('ok', False)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                free_channel_error = 'Channel not found or bot is not a member'
            elif e.code == 403:
                free_channel_error = 'Bot does not have permission to access this channel'
            else:
                free_channel_error = f'Telegram API error: {e.code}'
            logger.warning(f"Could not verify free channel: {free_channel_error}")
        except Exception as e:
            free_channel_error = f'Connection error: {str(e)}'
            logger.warning(f"Could not verify free channel: {e}")
        
        try:
            chat_id_param = vip_channel_id if vip_channel_id.startswith('-') else vip_channel_id
            url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={urllib.parse.quote(chat_id_param, safe='@')}"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                chat_info = json.loads(response.read().decode('utf-8'))
                vip_channel_verified = chat_info.get('ok', False)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                vip_channel_error = 'Channel not found or bot is not a member'
            elif e.code == 403:
                vip_channel_error = 'Bot does not have permission to access this channel'
            else:
                vip_channel_error = f'Telegram API error: {e.code}'
            logger.warning(f"Could not verify VIP channel: {vip_channel_error}")
        except Exception as e:
            vip_channel_error = f'Connection error: {str(e)}'
            logger.warning(f"Could not verify VIP channel: {e}")
        
        if not free_channel_verified:
            _send_json_response(handler, 400, {
                'success': False, 
                'error': f'Could not access Free channel: {free_channel_error or "Unknown error"}. Make sure the bot is an admin of this channel.'
            })
            return
        
        if not vip_channel_verified:
            _send_json_response(handler, 400, {
                'success': False, 
                'error': f'Could not access VIP channel: {vip_channel_error or "Unknown error"}. Make sure the bot is an admin of this channel.'
            })
            return
        
        integration_config = {
            'bot_token': bot_token,
            'bot_username': bot_username,
            'bot_name': bot_name,
            'free_channel_id': free_channel_id,
            'vip_channel_id': vip_channel_id,
            'verified_at': datetime.now().isoformat()
        }
        
        if not db.save_tenant_integration(tenant_id, 'telegram', integration_config):
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to save integration'})
            return
        
        step_data = {
            'bot_username': bot_username,
            'bot_name': bot_name,
            'free_channel_id': free_channel_id,
            'vip_channel_id': vip_channel_id,
            'verified': True
        }
        state = db.update_onboarding_step(tenant_id, 'telegram', step_data)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state,
                'bot_info': {
                    'username': bot_username,
                    'name': bot_name,
                    'free_channel_verified': free_channel_verified,
                    'vip_channel_verified': vip_channel_verified
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
    """POST /api/onboarding/stripe - Verify and save Stripe keys and webhook secret."""
    try:
        tenant_id = _require_tenant_id_or_create(handler)
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
        webhook_secret = data.get('webhook_secret', '').strip()
        
        if not secret_key:
            _send_json_response(handler, 400, {'success': False, 'error': 'secret_key is required'})
            return
        
        if not secret_key.startswith('sk_'):
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Stripe secret key format'})
            return
        
        if not publishable_key:
            _send_json_response(handler, 400, {'success': False, 'error': 'publishable_key is required'})
            return
        
        if not publishable_key.startswith('pk_'):
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid Stripe publishable key format'})
            return
        
        if not webhook_secret:
            _send_json_response(handler, 400, {'success': False, 'error': 'webhook_secret is required'})
            return
        
        if not webhook_secret.startswith('whsec_'):
            _send_json_response(handler, 400, {'success': False, 'error': 'Invalid webhook secret format (should start with whsec_)'})
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
            'publishable_key': publishable_key,
            'webhook_secret': webhook_secret,
            'is_live': is_live,
            'verified_at': datetime.now().isoformat()
        }
        
        if not db.save_tenant_integration(tenant_id, 'stripe', integration_config):
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to save integration'})
            return
        
        step_data = {
            'is_live': is_live,
            'has_webhook': True,
            'verified': True
        }
        state = db.update_onboarding_step(tenant_id, 'stripe', step_data)
        
        if state:
            _send_json_response(handler, 200, {
                'success': True,
                'state': state,
                'stripe_info': {
                    'is_live': is_live,
                    'has_publishable_key': True,
                    'has_webhook_secret': True
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
        tenant_id = _require_tenant_id_or_create(handler)
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
        
        # Also update the tenants table with display_name so it shows in admin
        db.update_tenant_display_name(tenant_id, display_name)
        
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
        tenant_id = _require_tenant_id_or_create(handler)
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
