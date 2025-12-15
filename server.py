#!/usr/bin/env python3
import http.server
import socketserver
import os
import json
import subprocess
import secrets
import base64
from urllib.parse import urlparse, parse_qs
import mimetypes
from http import cookies
import time
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

from core.logging import get_logger, set_request_context, clear_request_context
logger = get_logger(__name__)

from core.config import Config
from core.host_context import parse_host_context, HostType
from api.routes import GET_ROUTES, POST_ROUTES, PAGE_ROUTES, match_route, validate_routes
from api.middleware import apply_route_checks
from domains.subscriptions import handlers as subscription_handlers
from domains.coupons import handlers as coupon_handlers
from domains.forex import handlers as forex_handlers
from domains.tenant import handlers as tenant_handlers
from integrations.telegram.webhooks import handle_coupon_telegram_webhook, handle_forex_telegram_webhook
from integrations.stripe.webhooks import handle_stripe_webhook

OBJECT_STORAGE_AVAILABLE = False
TELEGRAM_BOT_AVAILABLE = False
DATABASE_AVAILABLE = False
COUPON_VALIDATOR_AVAILABLE = False
FOREX_SCHEDULER_AVAILABLE = False
STRIPE_AVAILABLE = False

db = None
coupon_validator = None
telegram_bot = None

try:
    from object_storage import ObjectStorageService
    OBJECT_STORAGE_AVAILABLE = True
except Exception as e:
    logger.info(f"Object storage not available: {e}")

PORT = Config.get_port()
DIRECTORY = "."
SESSION_TTL = 86400  # 24 hours in seconds

def create_signed_session():
    """Create a cryptographically signed session token that doesn't need server storage"""
    expiry = int(time.time()) + SESSION_TTL
    secret = Config.get_admin_password()
    if not secret:
        raise ValueError("ADMIN_PASSWORD environment variable must be set")
    
    # Create payload: expiry timestamp
    payload = str(expiry)
    
    # Create HMAC signature
    signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Combine payload and signature
    token = f"{payload}.{signature}"
    return token

def verify_signed_session(token):
    """Verify a signed session token without server-side storage"""
    try:
        if not token or '.' not in token:
            return False
        
        payload, signature = token.rsplit('.', 1)
        expiry = int(payload)
        
        # Check if expired
        if time.time() > expiry:
            logger.warning(f"Token expired: {expiry} < {time.time()}")
            return False
        
        # Verify signature
        secret = Config.get_admin_password()
        if not secret:
            logger.warning("ADMIN_PASSWORD not configured")
            return False
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if not is_valid:
            logger.warning("Invalid signature")
        
        return is_valid
    except Exception as e:
        logger.exception("Token verification error")
        return False

def log_tenant_context(tenant_id, request_path, request_id=None):
    """Log tenant context for audit trail. Raises if tenant_id missing on tenant-required paths."""
    import uuid
    req_id = request_id or str(uuid.uuid4())[:8]
    
    TENANT_REQUIRED_PATHS = ['/api/campaigns', '/api/forex', '/api/bot', '/api/telegram']
    
    if any(request_path.startswith(p) for p in TENANT_REQUIRED_PATHS):
        if not tenant_id:
            logger.error(f"Missing tenant_id on {request_path} (req={req_id})")
            raise ValueError(f"Tenant context required for {request_path}")
        logger.info(f"tenant={tenant_id} path={request_path} req={req_id}")

mimetypes.add_type('text/yaml', '.yml')
mimetypes.add_type('text/yaml', '.yaml')
mimetypes.add_type('application/json', '.json')

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def check_auth(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email
        
        clerk_user = get_auth_user_from_request(self)
        if clerk_user:
            # JWT is valid - use email from JWT if available, else trust X-Clerk-User-Email header
            email = clerk_user.get('email')
            if not email:
                email = self.headers.get('X-Clerk-User-Email')
            
            if is_admin_email(email):
                logger.debug(f"Clerk admin auth valid for: {email}")
                return True
            else:
                logger.debug(f"Clerk auth valid but not admin email: {email}")
                return False
        
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            logger.debug("No cookie header found")
            return False
        
        c = cookies.SimpleCookie()
        c.load(cookie_header)
        
        if 'admin_session' in c:
            token = c['admin_session'].value
            is_valid = verify_signed_session(token)
            logger.debug(f"Session token found, valid: {is_valid}")
            return is_valid
        
        logger.debug(f"No admin_session cookie found in: {cookie_header}")
        return False
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        host_header = self.headers.get('Host', '').lower()
        set_request_context(request_id=None)
        
        # Parse host context for routing decisions
        host_context = parse_host_context(host_header)
        self.host_context = host_context
        
        # Root path routing based on host
        if parsed_path.path == '/':
            if host_context.host_type == HostType.ADMIN:
                self.send_response(302)
                self.send_header('Location', '/admin')
                self.end_headers()
                return
            elif host_context.host_type == HostType.DASH:
                self.send_response(302)
                self.send_header('Location', '/app')
                self.end_headers()
                return
            else:
                self.send_response(302)
                self.send_header('Location', '/login')
                self.end_headers()
                return
        
        # Apply middleware checks via routing table (auth/db requirements)
        route = match_route('GET', parsed_path.path, GET_ROUTES + PAGE_ROUTES)
        if route:
            if not apply_route_checks(route, self, DATABASE_AVAILABLE, host_context.host_type):
                return  # Middleware sent 401/503 response
        
        # Dispatch to subscription domain handlers
        if parsed_path.path.startswith('/api/telegram/check-access/'):
            subscription_handlers.handle_telegram_check_access(self)
            return
        elif parsed_path.path == '/api/telegram-subscriptions':
            subscription_handlers.handle_telegram_subscriptions(self)
            return
        elif parsed_path.path == '/api/telegram/revenue-metrics':
            subscription_handlers.handle_telegram_revenue_metrics(self)
            return
        elif parsed_path.path == '/api/telegram/conversion-analytics':
            subscription_handlers.handle_telegram_conversion_analytics(self)
            return
        elif parsed_path.path.startswith('/api/telegram/billing/'):
            subscription_handlers.handle_telegram_billing(self)
            return
        
        # Dispatch to coupon domain handlers
        if parsed_path.path.startswith('/api/campaigns/') and '/submissions' in parsed_path.path:
            coupon_handlers.handle_campaign_submissions(self)
            return
        elif parsed_path.path.startswith('/api/campaigns/') and not parsed_path.path.endswith('/campaigns'):
            coupon_handlers.handle_campaign_by_id(self)
            return
        elif parsed_path.path == '/api/campaigns':
            coupon_handlers.handle_campaigns_list(self)
            return
        elif parsed_path.path == '/api/bot-stats':
            coupon_handlers.handle_bot_stats(self)
            return
        elif parsed_path.path == '/api/bot-users':
            coupon_handlers.handle_bot_users(self)
            return
        elif parsed_path.path.startswith('/api/broadcast-status/'):
            coupon_handlers.handle_broadcast_status(self)
            return
        elif parsed_path.path == '/api/broadcast-jobs':
            coupon_handlers.handle_broadcast_jobs(self)
            return
        elif parsed_path.path.startswith('/api/user-activity/'):
            coupon_handlers.handle_user_activity(self)
            return
        elif parsed_path.path == '/api/invalid-coupons':
            coupon_handlers.handle_invalid_coupons(self)
            return
        
        # Dispatch to forex domain handlers
        if parsed_path.path == '/api/forex-signals':
            forex_handlers.handle_forex_signals(self)
            return
        elif parsed_path.path == '/api/forex-config':
            forex_handlers.handle_forex_config(self)
            return
        elif parsed_path.path == '/api/forex-stats':
            forex_handlers.handle_forex_stats(self)
            return
        elif parsed_path.path == '/api/signal-bot/status':
            forex_handlers.handle_signal_bot_status(self)
            return
        elif parsed_path.path == '/api/forex-tp-config':
            forex_handlers.handle_forex_tp_config_get(self)
            return
        elif parsed_path.path == '/api/forex/xauusd-sparkline':
            forex_handlers.handle_xauusd_sparkline(self)
            return
        elif parsed_path.path == '/api/signal-bot/signals':
            forex_handlers.handle_signal_bot_signals(self)
            return
        
        # Dispatch to tenant domain handlers
        if parsed_path.path == '/api/tenant/setup-status':
            tenant_id = getattr(self, 'tenant_id', 'entrylab')
            set_request_context(tenant_id=tenant_id)
            tenant_handlers.handle_tenant_setup_status(self, tenant_id)
            return
        
        # Admin dashboard path
        if parsed_path.path == '/admin/':
            self.send_response(301)
            self.send_header('Location', '/admin')
            self.end_headers()
        elif parsed_path.path == '/admin':
            # Admin dashboard - accessible on admin host or dev environments
            if not host_context.is_dev and host_context.host_type == HostType.DASH:
                self.send_response(302)
                self.send_header('Location', 'https://admin.promostack.io/admin')
                self.end_headers()
                return
            
            try:
                with open('admin.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Admin page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path == '/app':
            # Client dashboard - accessible on dash host or dev environments
            if not host_context.is_dev and host_context.host_type == HostType.ADMIN:
                self.send_response(302)
                self.send_header('Location', 'https://dash.promostack.io/app')
                self.end_headers()
                return
            
            try:
                with open('app.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Client dashboard not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path == '/login':
            try:
                with open('login.html', 'r') as f:
                    content = f.read()
                clerk_key = Config.get_clerk_publishable_key() or ''
                content = content.replace('{{CLERK_PUBLISHABLE_KEY}}', clerk_key)
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Login page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path == '/coupon':
            try:
                with open('index.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Coupon page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path.startswith('/campaign/'):
            try:
                with open('campaign.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Campaign page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path == '/auth/me':
            try:
                from auth.clerk_auth import require_auth, AuthenticationError
                auth_user = require_auth(self)
                
                user_info = db.upsert_clerk_user(
                    clerk_user_id=auth_user['clerk_user_id'],
                    email=auth_user.get('email'),
                    name=auth_user.get('name'),
                    avatar_url=auth_user.get('avatar_url')
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'email': user_info.get('email'),
                    'name': user_info.get('name'),
                    'role': user_info.get('role'),
                    'tenant_id': user_info.get('tenant_id'),
                    'avatar_url': user_info.get('avatar_url'),
                    'clerk_user_id': user_info.get('clerk_user_id')
                }).encode())
            except AuthenticationError as e:
                self.send_response(e.status_code)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            except Exception as e:
                logger.exception("Error in /auth/me")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        
        elif parsed_path.path == '/api/check-auth':
            # Host-aware auth check - admin host requires ADMIN_EMAILS, dash host accepts any JWT
            from auth.clerk_auth import get_auth_user_from_request, is_admin_email
            clerk_user = get_auth_user_from_request(self)
            
            # Get email from query param (sent by frontend from Clerk user object)
            query_params = parse_qs(parsed_path.query)
            frontend_email = query_params.get('email', [None])[0]
            
            # Determine if admin check is required based on host
            require_admin = host_context.host_type != HostType.DASH
            
            if clerk_user:
                # JWT is valid - use email from JWT if available, else trust frontend email
                email = clerk_user.get('email') or frontend_email
                avatar = clerk_user.get('avatar_url')
                is_admin = is_admin_email(email)
                
                if require_admin and not is_admin:
                    # Admin host but not admin email - 403 Forbidden
                    self.send_response(403)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'authenticated': False,
                        'email': email,
                        'error': 'Access denied - not an admin email'
                    }).encode())
                else:
                    # Authenticated (and admin if required)
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'authenticated': True,
                        'email': email,
                        'avatar': avatar,
                        'is_admin': is_admin,
                        'host_type': host_context.host_type.value
                    }).encode())
            elif self.check_auth():
                # Legacy cookie auth (admin_session) - only for admin access
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'authenticated': True,
                    'email': None,
                    'avatar': None,
                    'is_admin': True,
                    'host_type': host_context.host_type.value
                }).encode())
            else:
                # Not authenticated at all
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'authenticated': False}).encode())
        
        elif parsed_path.path == '/api/day-of-week-stats':
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                query_params = parse_qs(parsed_path.query)
                days_param = query_params.get('days', [30])[0]
                
                # Handle both string ('today', 'yesterday') and integer (7, 30, 90) values
                if days_param in ['today', 'yesterday']:
                    days = days_param
                else:
                    days = int(days_param)
                
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id)
                result = db.get_day_of_week_stats(days, tenant_id=tenant_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                logger.exception("Error getting day-of-week stats")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/retention-rates':
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id)
                retention = db.get_retention_rates(tenant_id=tenant_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(retention).encode())
            except Exception as e:
                logger.exception("Error getting retention rates")
        
        elif parsed_path.path == '/api/metrics/tenant':
            import uuid
            request_id = str(uuid.uuid4())[:8]
            
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                query_params = parse_qs(parsed_path.query)
                days = int(query_params.get('days', [7])[0])
                
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id, request_id=request_id)
                logger.info(f"tenant={tenant_id} req={request_id} path=/api/metrics/tenant days={days}")
                
                metrics = db.get_tenant_metrics(tenant_id=tenant_id, days=days)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(metrics).encode())
            except Exception as e:
                logger.exception(f"Error getting tenant metrics: req={request_id}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif parsed_path.path == '/api/config':
            # Public endpoint to get frontend config (Clerk publishable key, etc.)
            # No auth required - this is public configuration data
            try:
                clerk_key = Config.get_clerk_publishable_key() or ''
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'public, max-age=3600')  # Cache for 1 hour
                self.end_headers()
                self.wfile.write(json.dumps({
                    'clerkPublishableKey': clerk_key
                }).encode())
            except Exception as e:
                logger.exception("Error getting config")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        
        elif parsed_path.path == '/api/telegram-channel-stats':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                import asyncio
                from telegram import Bot
                
                free_channel = "@entrylabs"
                vip_channel_id = Config.get_forex_channel_id()
                bot_token = Config.get_forex_bot_token()
                
                result = {
                    'free_channel': {
                        'name': free_channel,
                        'member_count': None
                    },
                    'vip_channel': {
                        'name': 'VIP Signals',
                        'member_count': None
                    }
                }
                
                if bot_token:
                    bot = Bot(token=bot_token)
                    
                    async def get_channel_counts():
                        counts = {'free': None, 'vip': None}
                        try:
                            free_chat = await bot.get_chat(free_channel)
                            counts['free'] = await bot.get_chat_member_count(free_channel)
                        except Exception as e:
                            logger.warning(f"Error getting free channel count: {e}")
                        
                        if vip_channel_id:
                            try:
                                vip_chat = await bot.get_chat(vip_channel_id)
                                counts['vip'] = await bot.get_chat_member_count(vip_channel_id)
                                result['vip_channel']['name'] = vip_chat.title or 'VIP Signals'
                            except Exception as e:
                                logger.warning(f"Error getting VIP channel count: {e}")
                        
                        return counts
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    counts = loop.run_until_complete(get_channel_counts())
                    loop.close()
                    
                    result['free_channel']['member_count'] = counts.get('free')
                    result['vip_channel']['member_count'] = counts.get('vip')
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                logger.exception("Error getting channel stats")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
        elif parsed_path.path == '/':
            # Default homepage: redirect to login (not admin.promostack.io or dash.promostack.io)
            self.send_response(302)
            self.send_header('Location', '/login')
            self.end_headers()
        else:
            super().do_GET()
        clear_request_context()
    def do_POST(self):
        parsed_path = urlparse(self.path)
        set_request_context(request_id=None)
        
        # Apply middleware checks via routing table (auth/db requirements)
        route = match_route('POST', parsed_path.path, POST_ROUTES)
        if route:
            if not apply_route_checks(route, self, DATABASE_AVAILABLE):
                return  # Middleware sent 401/503 response
        
        # Dispatch to subscription domain handlers
        if parsed_path.path == '/api/telegram/grant-access':
            subscription_handlers.handle_telegram_grant_access(self)
            return
        elif parsed_path.path == '/api/telegram/clear-all':
            subscription_handlers.handle_telegram_clear_all(self)
            return
        elif parsed_path.path == '/api/telegram/cleanup-test-data':
            subscription_handlers.handle_telegram_cleanup_test_data(self)
            return
        elif parsed_path.path == '/api/telegram/cancel-subscription':
            subscription_handlers.handle_telegram_cancel_subscription(self)
            return
        elif parsed_path.path == '/api/telegram/delete-subscription':
            subscription_handlers.handle_telegram_delete_subscription(self)
            return
        elif parsed_path.path == '/api/telegram/revoke-access':
            subscription_handlers.handle_telegram_revoke_access(self)
            return
        
        # Dispatch to coupon domain handlers
        if parsed_path.path == '/api/validate-coupon':
            coupon_handlers.handle_validate_coupon(self)
            return
        elif parsed_path.path.startswith('/api/campaigns/') and '/submit' in parsed_path.path:
            coupon_handlers.handle_campaign_submit(self)
            return
        elif parsed_path.path.startswith('/api/campaigns/') and '/update' in parsed_path.path:
            coupon_handlers.handle_campaign_update(self)
            return
        elif parsed_path.path.startswith('/api/campaigns/') and '/delete' in parsed_path.path:
            coupon_handlers.handle_campaign_delete(self)
            return
        elif parsed_path.path == '/api/campaigns':
            coupon_handlers.handle_campaigns_create(self)
            return
        elif parsed_path.path == '/api/broadcast':
            coupon_handlers.handle_broadcast(self)
            return
        elif parsed_path.path == '/api/upload-overlay':
            coupon_handlers.handle_upload_overlay(self)
            return
        elif parsed_path.path == '/api/upload-template':
            coupon_handlers.handle_upload_template(self)
            return
        elif parsed_path.path == '/api/delete-template':
            coupon_handlers.handle_delete_template(self)
            return
        elif parsed_path.path == '/api/toggle-telegram-template':
            coupon_handlers.handle_toggle_telegram_template(self)
            return
        elif parsed_path.path == '/api/clear-telegram-cache':
            coupon_handlers.handle_clear_telegram_cache(self)
            return
        elif parsed_path.path == '/api/regenerate-index':
            coupon_handlers.handle_regenerate_index(self)
            return
        
        # Dispatch to forex domain handlers
        if parsed_path.path == '/api/forex-config':
            forex_handlers.handle_forex_config_post(self)
            return
        elif parsed_path.path == '/api/forex-tp-config':
            forex_handlers.handle_forex_tp_config_post(self)
            return
        elif parsed_path.path == '/api/signal-bot/set-active':
            forex_handlers.handle_signal_bot_set_active(self)
            return
        elif parsed_path.path == '/api/signal-bot/cancel-queue':
            forex_handlers.handle_signal_bot_cancel_queue(self)
            return
        
        # Dispatch to tenant domain handlers
        if parsed_path.path == '/api/tenant/integrations':
            tenant_id = getattr(self, 'tenant_id', 'entrylab')
            set_request_context(tenant_id=tenant_id)
            tenant_handlers.handle_tenant_integrations(self, tenant_id)
            return
        elif parsed_path.path == '/api/tenants/map-user':
            tenant_handlers.handle_tenant_map_user(self)
            return
        
        # Dispatch to telegram webhook handlers
        if parsed_path.path == '/api/telegram-webhook':
            handle_coupon_telegram_webhook(self, TELEGRAM_BOT_AVAILABLE, telegram_bot)
            return
        elif parsed_path.path == '/api/forex-telegram-webhook':
            handle_forex_telegram_webhook(self, TELEGRAM_BOT_AVAILABLE, telegram_bot)
            return
        
        # Dispatch to stripe webhook handler
        if parsed_path.path == '/api/stripe/webhook':
            handle_stripe_webhook(self, STRIPE_AVAILABLE, TELEGRAM_BOT_AVAILABLE, db)
            return
        # TODO: REMOVE STATIC PASSWORD LOGIN - This is legacy auth that should be removed
        # once Clerk Google login is fully working. To remove:
        # 1. Delete this /api/login endpoint
        # 2. Delete create_signed_session() and verify_signed_session() functions
        # 3. Update check_auth() to only use Clerk authentication
        # 4. Also remove related code in admin.html (see TODO there)
        elif parsed_path.path == '/api/login':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                password = data.get('password', '')
                admin_password = Config.get_admin_password() or ''
                
                if password == admin_password and admin_password:
                    session_token = create_signed_session()
                    
                    # Add Secure flag for HTTPS (Digital Ocean runs on port 8080 with HTTPS)
                    is_production = PORT == 8080 or Config.get_app_url().startswith('https')
                    secure_flag = '; Secure' if is_production else ''
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Set-Cookie', f'admin_session={session_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{secure_flag}')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                else:
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Invalid password'}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/auth/logout':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif parsed_path.path == '/api/logout':
            # No server-side cleanup needed with signed cookies
            # Just clear the cookie on the client side
            
            # Add Secure flag for HTTPS (Digital Ocean runs on port 8080 with HTTPS)
            is_production = PORT == 8080 or Config.get_app_url().startswith('https')
            secure_flag = '; Secure' if is_production else ''
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Set-Cookie', f'admin_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_flag}')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif parsed_path.path == '/api/stripe/sync':
            # Admin API - Sync all active subscriptions from Stripe to database
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            if not STRIPE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Stripe not available'}).encode())
                return
            
            try:
                from stripe_client import fetch_active_subscriptions
                
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id)
                
                subscriptions = fetch_active_subscriptions()
                synced = 0
                errors = []
                
                for sub in subscriptions:
                    if sub.get('email'):
                        result, error = db.create_or_update_telegram_subscription(
                            email=sub['email'],
                            stripe_customer_id=sub.get('customer_id'),
                            stripe_subscription_id=sub.get('subscription_id'),
                            plan_type=sub.get('plan_name') or 'premium',
                            amount_paid=sub.get('amount_paid', 0),
                            name=sub.get('name'),
                            tenant_id=tenant_id
                        )
                        if result:
                            synced += 1
                            logger.info(f"Synced: {sub['email']}")
                        else:
                            errors.append(f"{sub['email']}: {error}")
                            logger.warning(f"Failed: {sub['email']} - {error}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'synced': synced,
                    'total': len(subscriptions),
                    'errors': errors
                }).encode())
                
            except Exception as e:
                logger.exception("Stripe sync error")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
        clear_request_context()
    def do_PUT(self):
        parsed_path = urlparse(self.path)
        set_request_context(request_id=None)
        
        if parsed_path.path.startswith('/api/campaigns/'):
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id)
                db.update_campaign(
                    campaign_id=campaign_id,
                    title=data['title'],
                    description=data.get('description', ''),
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    prize=data.get('prize', ''),
                    platforms=json.dumps(data.get('platforms', [])),
                    overlay_url=data.get('overlay_url'),
                    tenant_id=tenant_id
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                logger.exception("Error updating campaign")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
        clear_request_context()
    
    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        set_request_context(request_id=None)
        
        if parsed_path.path.startswith('/api/campaigns/'):
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                tenant_id = getattr(self, 'tenant_id', 'entrylab')
                set_request_context(tenant_id=tenant_id)
                db.delete_campaign(campaign_id, tenant_id=tenant_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                logger.exception("Error deleting campaign")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
        clear_request_context()

if __name__ == "__main__":
    # Note: validate_routes(MyHTTPRequestHandler) will be called in Step 9
    # after handlers are extracted to methods
    
    from core.app_context import create_app_context
    from core.bootstrap import start_app
    
    ctx = create_app_context()
    start_app(ctx)
    
    import sys
    sys.modules['server'] = sys.modules[__name__]
    
    import db as db_module
    import telegram_bot as tb_module
    import coupon_validator as cv_module
    db = db_module
    telegram_bot = tb_module
    coupon_validator = cv_module
    DATABASE_AVAILABLE = ctx.database_available
    TELEGRAM_BOT_AVAILABLE = ctx.telegram_bot_available
    COUPON_VALIDATOR_AVAILABLE = ctx.coupon_validator_available
    FOREX_SCHEDULER_AVAILABLE = ctx.forex_scheduler_available
    STRIPE_AVAILABLE = ctx.stripe_available
    OBJECT_STORAGE_AVAILABLE = ctx.object_storage_available
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Server running at http://0.0.0.0:{PORT}/")
        print(f"Serving files from {os.path.abspath(DIRECTORY)}")
        print(f"API endpoints:")
        print(f"  POST /api/validate-coupon")
        print(f"  POST /api/login")
        print(f"  POST /api/logout")
        print(f"  POST /api/upload-template (requires auth)")
        print(f"  POST /api/delete-template (requires auth)")
        print(f"  POST /api/regenerate-index")
        print(f"  POST /api/telegram-webhook")
        print(f"  POST /api/forex-telegram-webhook")
        print(f"  GET  /api/forex-signals (requires auth)")
        print(f"  GET  /api/forex-stats (requires auth)")
        httpd.serve_forever()
