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

from core.config import Config
from api.routes import GET_ROUTES, POST_ROUTES, PAGE_ROUTES, match_route, validate_routes
from api.middleware import apply_route_checks
from domains.subscriptions import handlers as subscription_handlers
from domains.coupons import handlers as coupon_handlers
from domains.forex import handlers as forex_handlers
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
    print(f"[INFO] Object storage not available: {e}")

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
            print(f"[AUTH] Token expired: {expiry} < {time.time()}")
            return False
        
        # Verify signature
        secret = Config.get_admin_password()
        if not secret:
            print(f"[AUTH] ADMIN_PASSWORD not configured")
            return False
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if not is_valid:
            print(f"[AUTH] Invalid signature")
        
        return is_valid
    except Exception as e:
        print(f"[AUTH] Token verification error: {e}")
        return False

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
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            print(f"[AUTH] No cookie header found")
            return False
        
        c = cookies.SimpleCookie()
        c.load(cookie_header)
        
        if 'admin_session' in c:
            token = c['admin_session'].value
            is_valid = verify_signed_session(token)
            print(f"[AUTH] Session token found, valid: {is_valid}")
            return is_valid
        
        print(f"[AUTH] No admin_session cookie found in: {cookie_header}")
        return False
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        host = self.headers.get('Host', '').lower()
        
        # Domain-based routing for custom domains
        if 'admin.promostack.io' in host and parsed_path.path == '/':
            try:
                with open('admin.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_error(404, "Admin page not found")
                return
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
                return
        
        elif 'dash.promostack.io' in host and parsed_path.path == '/':
            try:
                with open('index.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_error(404, "Frontend page not found")
                return
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
                return
        
        # Apply middleware checks via routing table (auth/db requirements)
        route = match_route('GET', parsed_path.path, GET_ROUTES + PAGE_ROUTES)
        if route:
            if not apply_route_checks(route, self, DATABASE_AVAILABLE):
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
        
        # Legacy /admin path support - redirect to admin.promostack.io
        if parsed_path.path == '/admin/':
            self.send_response(301)
            self.send_header('Location', '/admin')
            self.end_headers()
        elif parsed_path.path == '/admin':
            # Dev mode: serve admin panel directly on localhost/replit
            # Production: redirect to admin.promostack.io
            is_dev = 'localhost' in host or '127.0.0.1' in host or 'replit' in host or ':' in host
            
            if not is_dev and 'admin.promostack.io' not in host:
                self.send_response(301)
                self.send_header('Location', 'https://admin.promostack.io')
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
        
        elif parsed_path.path == '/api/check-auth':
            # Check if user is authenticated (for page refresh)
            if self.check_auth():
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'authenticated': True}).encode())
            else:
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
                
                result = db.get_day_of_week_stats(days)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                print(f"[API] Error getting day-of-week stats: {e}")
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
                retention = db.get_retention_rates()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(retention).encode())
            except Exception as e:
                print(f"[API] Error getting retention rates: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
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
                            print(f"[TELEGRAM] Error getting free channel count: {e}")
                        
                        if vip_channel_id:
                            try:
                                vip_chat = await bot.get_chat(vip_channel_id)
                                counts['vip'] = await bot.get_chat_member_count(vip_channel_id)
                                result['vip_channel']['name'] = vip_chat.title or 'VIP Signals'
                            except Exception as e:
                                print(f"[TELEGRAM] Error getting VIP channel count: {e}")
                        
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
                print(f"[TELEGRAM] Error getting channel stats: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
        else:
            super().do_GET()
    def do_POST(self):
        parsed_path = urlparse(self.path)
        
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
                            name=sub.get('name')
                        )
                        if result:
                            synced += 1
                            print(f"[STRIPE SYNC] Synced: {sub['email']}")
                        else:
                            errors.append(f"{sub['email']}: {error}")
                            print(f"[STRIPE SYNC] Failed: {sub['email']} - {error}")
                
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
                print(f"[STRIPE SYNC] Error: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
    def do_PUT(self):
        parsed_path = urlparse(self.path)
        
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
                
                db.update_campaign(
                    campaign_id=campaign_id,
                    title=data['title'],
                    description=data.get('description', ''),
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    prize=data.get('prize', ''),
                    platforms=json.dumps(data.get('platforms', [])),
                    overlay_url=data.get('overlay_url')
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error updating campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
    
    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        
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
                db.delete_campaign(campaign_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error deleting campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")

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
