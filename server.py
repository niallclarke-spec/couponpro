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
import cgi
from http import cookies
import time
import hmac
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Try to import object storage (only available on Replit)
try:
    from object_storage import ObjectStorageService
    OBJECT_STORAGE_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Object storage not available (running outside Replit): {e}")
    OBJECT_STORAGE_AVAILABLE = False

# Import Telegram bot handler
try:
    import telegram_bot
    TELEGRAM_BOT_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Telegram bot not available: {e}")
    TELEGRAM_BOT_AVAILABLE = False

# Import database module for campaigns
try:
    import db
    schema_initialized = db.db_pool.initialize_schema()
    DATABASE_AVAILABLE = schema_initialized
    if not DATABASE_AVAILABLE:
        print(f"[INFO] Database not available - campaigns feature disabled")
except Exception as e:
    print(f"[INFO] Database not available: {e}")
    DATABASE_AVAILABLE = False

# Import coupon validator for FunderPro integration
try:
    import coupon_validator
    COUPON_VALIDATOR_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Coupon validator not available: {e}")
    COUPON_VALIDATOR_AVAILABLE = False

# Import forex signals scheduler
try:
    from forex_scheduler import start_forex_scheduler
    FOREX_SCHEDULER_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Forex scheduler not available: {e}")
    FOREX_SCHEDULER_AVAILABLE = False

# Import Stripe client for revenue metrics
try:
    from stripe_client import get_stripe_client
    get_stripe_client()  # Test that credentials are available
    STRIPE_AVAILABLE = True
    print("[INFO] Stripe client initialized")
except Exception as e:
    print(f"[INFO] Stripe not available: {e}")
    STRIPE_AVAILABLE = False

PORT = int(os.environ.get('PORT', 5000))
DIRECTORY = "."
SESSION_TTL = 86400  # 24 hours in seconds

def create_signed_session():
    """Create a cryptographically signed session token that doesn't need server storage"""
    expiry = int(time.time()) + SESSION_TTL
    secret = os.environ.get('ADMIN_PASSWORD')
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
        secret = os.environ.get('ADMIN_PASSWORD')
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
        
        elif parsed_path.path == '/api/campaigns':
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                db.update_campaign_statuses()
                campaigns = db.get_all_campaigns()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(campaigns).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting campaigns: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submissions' in parsed_path.path:
            # Get campaign submissions - handled below
            pass
        
        elif parsed_path.path.startswith('/api/campaigns/'):
            # Get single campaign by ID
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                campaign = db.get_campaign_by_id(campaign_id)
                
                if campaign:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True, 'campaign': campaign}).encode())
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Campaign not found'}).encode())
            except (IndexError, ValueError):
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid campaign ID'}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submissions' in parsed_path.path:
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
                submissions = db.get_campaign_submissions(campaign_id)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(submissions).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting submissions: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/bot-stats':
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
                days_param = query_params.get('days', ['30'])[0]
                template = query_params.get('template', [None])[0]
                
                # Sanitize template parameter - convert "null", "", "all" to None
                if template in [None, '', 'null', 'all']:
                    template = None
                
                # Support 'today', 'yesterday', or numeric days
                if days_param in ['today', 'yesterday']:
                    days = days_param
                else:
                    days = int(days_param)
                
                stats = db.get_bot_stats(days, template_filter=template)
                
                if stats:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(stats).encode())
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'total_uses': 0,
                        'successful_uses': 0,
                        'success_rate': 0,
                        'unique_users': 0,
                        'popular_templates': [],
                        'popular_coupons': [],
                        'errors': [],
                        'daily_usage': []
                    }).encode())
            except Exception as e:
                print(f"[BOT_STATS] Error getting bot stats: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
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
        
        elif parsed_path.path == '/api/forex-signals':
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
                from db import get_forex_signals
                query_params = parse_qs(parsed_path.query)
                status_filter = query_params.get('status', [None])[0]
                limit = int(query_params.get('limit', [100])[0])
                
                signals = get_forex_signals(status=status_filter, limit=limit)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(signals).encode())
            except Exception as e:
                print(f"[FOREX] Error getting signals: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/forex-config':
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
                from db import get_forex_config
                config = get_forex_config()
                
                if config:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(config).encode())
                else:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Failed to load config'}).encode())
            except Exception as e:
                print(f"[FOREX] Error getting config: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/forex-stats':
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
                from db import get_forex_stats
                query_params = parse_qs(parsed_path.query)
                days = int(query_params.get('days', [7])[0])
                
                stats = get_forex_stats(days=days)
                
                if stats:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(stats).encode())
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'total_signals': 0,
                        'won_signals': 0,
                        'lost_signals': 0,
                        'pending_signals': 0,
                        'win_rate': 0,
                        'total_pips': 0,
                        'signals_by_pair': [],
                        'daily_signals': []
                    }).encode())
            except Exception as e:
                print(f"[FOREX] Error getting stats: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/signal-bot/status':
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
                from db import get_active_bot, get_open_signal, get_signals_by_bot_type
                
                active_bot = get_active_bot()
                open_signal = get_open_signal()
                
                aggressive_signals = get_signals_by_bot_type('aggressive', limit=10)
                conservative_signals = get_signals_by_bot_type('conservative', limit=10)
                custom_signals = get_signals_by_bot_type('custom', limit=10)
                legacy_signals = get_signals_by_bot_type('legacy', limit=10)
                
                status = {
                    'active_bot': active_bot or 'aggressive',
                    'available_bots': ['aggressive', 'conservative', 'custom'],
                    'open_signal': open_signal,
                    'recent_signals': {
                        'aggressive': len(aggressive_signals),
                        'conservative': len(conservative_signals),
                        'custom': len(custom_signals),
                        'legacy': len(legacy_signals)
                    }
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(status).encode())
            except Exception as e:
                print(f"[SIGNAL BOT] Error getting status: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/signal-bot/signals':
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
                from db import get_signals_by_bot_type, get_forex_signals
                query_params = parse_qs(parsed_path.query)
                bot_type = query_params.get('bot_type', [None])[0]
                status_filter = query_params.get('status', [None])[0]
                limit = int(query_params.get('limit', [50])[0])
                
                if bot_type:
                    signals = get_signals_by_bot_type(bot_type, status=status_filter, limit=limit)
                else:
                    signals = get_forex_signals(status=status_filter, limit=limit)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(signals).encode())
            except Exception as e:
                print(f"[SIGNAL BOT] Error getting signals: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/telegram/check-access/'):
            # EntryLab API - Check subscription access status by email
            api_key = self.headers.get('X-API-Key') or self.headers.get('Authorization', '').replace('Bearer ', '')
            expected_key = os.environ.get('ENTRYLAB_API_KEY', '')
            
            if not api_key or api_key != expected_key or not expected_key:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'hasAccess': False, 'error': 'Unauthorized - Invalid API key'}).encode())
                return
            
            try:
                # Extract email from path (URL-encoded)
                from urllib.parse import unquote
                email = unquote(parsed_path.path.split('/api/telegram/check-access/')[1])
                
                if not email:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'hasAccess': False, 'error': 'Email parameter required'}).encode())
                    return
                
                # Get subscription from database
                subscription = db.get_telegram_subscription_by_email(email)
                
                if not subscription:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'hasAccess': False,
                        'error': f'No subscription found for {email}'
                    }).encode())
                    return
                
                has_access = subscription['status'] == 'active' and subscription['telegram_user_id'] is not None
                
                response_data = {
                    'hasAccess': has_access,
                    'telegramUserId': subscription.get('telegram_user_id'),
                    'telegramUsername': subscription.get('telegram_username'),
                    'status': subscription.get('status'),
                    'joinedAt': subscription.get('joined_at'),
                    'lastSeenAt': subscription.get('last_seen_at')
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                
            except Exception as e:
                print(f"[TELEGRAM-SUB] Error checking access: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'hasAccess': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram-subscriptions':
            # Admin endpoint - Get all telegram subscriptions for dashboard
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
                status_filter = query_params.get('status', [None])[0]
                include_test = query_params.get('include_test', ['false'])[0].lower() == 'true'
                
                subscriptions = db.get_all_telegram_subscriptions(status_filter=status_filter, include_test=include_test)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'subscriptions': subscriptions}).encode())
            except Exception as e:
                print(f"[TELEGRAM-SUB] Error getting subscriptions: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/revenue-metrics':
            # Admin endpoint - Get revenue metrics DIRECTLY FROM STRIPE
            # Best practice: Stripe is source of truth for all financial data
            # IMPORTANT: Filter to only PromoStack subscriptions (not entire Stripe account)
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                if not STRIPE_AVAILABLE:
                    raise Exception("Stripe not configured")
                
                # Get subscription IDs from our database to filter Stripe data
                subscriptions = db.get_all_telegram_subscriptions()
                stripe_sub_ids = [s.get('stripe_subscription_id') for s in subscriptions if s.get('stripe_subscription_id')]
                
                from stripe_client import get_stripe_metrics
                
                print(f"[REVENUE] Fetching metrics for {len(stripe_sub_ids)} PromoStack subscriptions...")
                metrics = get_stripe_metrics(subscription_ids=stripe_sub_ids)
                
                if metrics:
                    print(f"[REVENUE] Stripe returned: revenue=${metrics.get('total_revenue')}, rebill=${metrics.get('monthly_rebill')}")
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(metrics).encode())
                else:
                    raise Exception("Failed to fetch metrics from Stripe")
                
            except Exception as e:
                print(f"[REVENUE] Error getting metrics: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/conversion-analytics':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                analytics = db.get_conversion_analytics()
                
                if analytics:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(analytics).encode())
                else:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Failed to fetch conversion analytics'}).encode())
                
            except Exception as e:
                print(f"[CONVERSIONS] Error getting analytics: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/telegram/billing/'):
            # Admin endpoint - Get billing info from Stripe for a subscription
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                # Extract subscription ID from path
                subscription_id = parsed_path.path.split('/api/telegram/billing/')[1]
                
                if not subscription_id:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Subscription ID required'}).encode())
                    return
                
                # Get subscription from our database first
                subscription = db.get_telegram_subscription_by_id(int(subscription_id))
                
                if not subscription:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Subscription not found'}).encode())
                    return
                
                stripe_customer_id = subscription.get('stripe_customer_id')
                stripe_subscription_id = subscription.get('stripe_subscription_id')
                amount_paid = float(subscription.get('amount_paid') or 0)
                
                # For free users, return subscription data without billing
                if amount_paid == 0:
                    response_data = {
                        'subscription': subscription,
                        'billing': None,
                        'billing_status': 'free_user'
                    }
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode())
                    return
                
                # For paid users, we need Stripe IDs
                if not stripe_subscription_id and not stripe_customer_id:
                    response_data = {
                        'subscription': subscription,
                        'billing': None,
                        'billing_status': 'no_stripe_ids',
                        'error': 'No Stripe subscription or customer ID linked'
                    }
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode())
                    return
                
                # Try to fetch billing from Stripe
                billing_info = None
                billing_error = None
                
                if stripe_subscription_id:
                    try:
                        from stripe_client import get_subscription_billing_info
                        billing_info = get_subscription_billing_info(stripe_subscription_id)
                        if billing_info and billing_info.get('error'):
                            billing_error = billing_info.get('error')
                            billing_info = None
                    except Exception as stripe_err:
                        print(f"[BILLING] Error fetching subscription from Stripe: {stripe_err}")
                        billing_error = str(stripe_err)
                
                # Fall back to customer info if subscription fetch failed
                if not billing_info and stripe_customer_id:
                    try:
                        from stripe_client import get_customer_billing_info
                        billing_info = get_customer_billing_info(stripe_customer_id)
                        if billing_info and billing_info.get('error'):
                            billing_error = billing_info.get('error')
                            billing_info = None
                    except Exception as stripe_err:
                        print(f"[BILLING] Error fetching customer from Stripe: {stripe_err}")
                        billing_error = str(stripe_err)
                
                # Build response based on what we got
                if billing_info:
                    response_data = {
                        'subscription': subscription,
                        'billing': billing_info,
                        'billing_status': 'success'
                    }
                    self.send_response(200)
                else:
                    response_data = {
                        'subscription': subscription,
                        'billing': None,
                        'billing_status': 'stripe_error',
                        'error': billing_error or 'Unable to fetch billing info from Stripe'
                    }
                    self.send_response(200)  # Still 200 so frontend can handle gracefully
                
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                
            except Exception as e:
                print(f"[BILLING] Error getting billing info: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/broadcast-status/'):
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
                job_id = int(parsed_path.path.split('/')[-1])
                job = db.get_broadcast_job(job_id)
                
                if job:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(job).encode())
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Job not found'}).encode())
            except Exception as e:
                print(f"[BROADCAST] Error getting job status: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/broadcast-jobs':
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
                jobs = db.get_recent_broadcast_jobs(limit=20)
                user_count = db.get_bot_user_count(days=30)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'jobs': jobs,
                    'active_users': user_count
                }).encode())
            except Exception as e:
                print(f"[BROADCAST] Error getting broadcast jobs: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/bot-users':
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
                limit = int(query_params.get('limit', ['100'])[0])
                offset = int(query_params.get('offset', ['0'])[0])
                
                result = db.get_all_bot_users(limit=limit, offset=offset)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                print(f"[API] Error getting bot users: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/user-activity/'):
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
                # Extract chat_id from path
                chat_id = int(parsed_path.path.split('/')[-1])
                
                # Get user info and activity history
                user = db.get_bot_user(chat_id)
                history = db.get_user_activity_history(chat_id, limit=100)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'user': user,
                    'history': history
                }).encode())
            except Exception as e:
                print(f"[API] Error getting user activity: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/invalid-coupons':
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
                limit = int(query_params.get('limit', ['100'])[0])
                offset = int(query_params.get('offset', ['0'])[0])
                template_filter = query_params.get('template', [None])[0]
                days_param = query_params.get('days', [None])[0]
                
                # Validate and sanitize days parameter
                days = None
                if days_param:
                    try:
                        days = int(days_param)
                        # Enforce reasonable bounds (1-365 days)
                        if days < 1 or days > 365:
                            days = 30  # Default to 30 days if out of bounds
                    except (ValueError, TypeError):
                        days = 30  # Default to 30 days on invalid input
                
                result = db.get_invalid_coupon_attempts(
                    limit=limit, 
                    offset=offset, 
                    template_filter=template_filter,
                    days=days
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                print(f"[API] Error getting invalid coupons: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else:
            super().do_GET()
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/validate-coupon':
            if not COUPON_VALIDATOR_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'valid': False,
                    'message': 'Coupon validation service unavailable'
                }).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                coupon_code = data.get('coupon_code', '').strip()
                
                if not coupon_code:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'valid': False,
                        'message': 'Coupon code is required'
                    }).encode())
                    return
                
                # Validate coupon with FunderPro API
                result = coupon_validator.validate_coupon(coupon_code)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'valid': False,
                    'message': 'Invalid request format'
                }).encode())
            except Exception as e:
                print(f"[COUPON] Validation error: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'valid': False,
                    'message': 'Server error during validation'
                }).encode())
        
        elif parsed_path.path == '/api/broadcast':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Database not available'
                }).encode())
                return
            
            if not TELEGRAM_BOT_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Telegram bot not available'
                }).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                message = data.get('message', '').strip()
                days = int(data.get('days', 30))
                
                if not message:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'error': 'Message is required'
                    }).encode())
                    return
                
                # Get active users
                users = db.get_active_bot_users(days)
                
                if not users:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'sent': 0,
                        'failed': 0,
                        'total': 0,
                        'message': 'No active users found'
                    }).encode())
                    return
                
                # Send broadcast using telegram_bot
                result = telegram_bot.send_broadcast(users, message)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': 'Invalid request format'
                }).encode())
            except Exception as e:
                print(f"[BROADCAST] Error: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': str(e)
                }).encode())
        
        elif parsed_path.path == '/api/login':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                password = data.get('password', '')
                admin_password = os.environ.get('ADMIN_PASSWORD', '')
                
                if password == admin_password and admin_password:
                    session_token = create_signed_session()
                    
                    # Add Secure flag for HTTPS (Digital Ocean runs on port 8080 with HTTPS)
                    is_production = PORT == 8080 or os.environ.get('APP_URL', '').startswith('https')
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
            is_production = PORT == 8080 or os.environ.get('APP_URL', '').startswith('https')
            secure_flag = '; Secure' if is_production else ''
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Set-Cookie', f'admin_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_flag}')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif parsed_path.path == '/api/forex-config':
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
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # Validate config values
                valid_keys = ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 
                             'atr_sl_multiplier', 'atr_tp_multiplier', 
                             'trading_start_hour', 'trading_end_hour']
                
                config_updates = {}
                errors = []
                
                for key in valid_keys:
                    if key in data:
                        value = data[key]
                        
                        # Validate based on key type
                        if key in ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 'trading_start_hour', 'trading_end_hour']:
                            try:
                                int_value = int(value)
                                # Additional validation
                                if key == 'rsi_oversold' and not (0 <= int_value <= 100):
                                    errors.append(f'{key} must be between 0 and 100')
                                elif key == 'rsi_overbought' and not (0 <= int_value <= 100):
                                    errors.append(f'{key} must be between 0 and 100')
                                elif key == 'adx_threshold' and not (0 <= int_value <= 100):
                                    errors.append(f'{key} must be between 0 and 100')
                                elif key == 'trading_start_hour' and not (0 <= int_value <= 23):
                                    errors.append(f'{key} must be between 0 and 23')
                                elif key == 'trading_end_hour' and not (0 <= int_value <= 23):
                                    errors.append(f'{key} must be between 0 and 23')
                                else:
                                    config_updates[key] = int_value
                            except ValueError:
                                errors.append(f'{key} must be an integer')
                        
                        elif key in ['atr_sl_multiplier', 'atr_tp_multiplier']:
                            try:
                                float_value = float(value)
                                if float_value <= 0:
                                    errors.append(f'{key} must be greater than 0')
                                else:
                                    config_updates[key] = float_value
                            except ValueError:
                                errors.append(f'{key} must be a number')
                
                # Cross-field validation
                if 'trading_start_hour' in config_updates and 'trading_end_hour' in config_updates:
                    if config_updates['trading_start_hour'] >= config_updates['trading_end_hour']:
                        errors.append('trading_start_hour must be less than trading_end_hour')
                elif 'trading_start_hour' in config_updates or 'trading_end_hour' in config_updates:
                    # If only one is being updated, validate against existing config
                    from db import get_forex_config
                    current_config = get_forex_config() or {}
                    start_hour = config_updates.get('trading_start_hour', current_config.get('trading_start_hour', 8))
                    end_hour = config_updates.get('trading_end_hour', current_config.get('trading_end_hour', 22))
                    if start_hour >= end_hour:
                        errors.append('trading_start_hour must be less than trading_end_hour')
                
                # RSI validation - oversold must be less than overbought
                if 'rsi_oversold' in config_updates and 'rsi_overbought' in config_updates:
                    if config_updates['rsi_oversold'] >= config_updates['rsi_overbought']:
                        errors.append('rsi_oversold must be less than rsi_overbought')
                
                if errors:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': ', '.join(errors)}).encode())
                    return
                
                if not config_updates:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'No valid config values provided'}).encode())
                    return
                
                # Update config in database
                from db import update_forex_config
                update_forex_config(config_updates)
                
                # Reload config in forex signal engine
                if FOREX_SCHEDULER_AVAILABLE:
                    from forex_signals import forex_signal_engine
                    forex_signal_engine.reload_config()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': 'Configuration updated successfully'
                }).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid request format'}).encode())
            except Exception as e:
                print(f"[FOREX] Error updating config: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/signal-bot/set-active':
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
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                bot_type = data.get('bot_type')
                
                if not bot_type:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'bot_type is required'}).encode())
                    return
                
                valid_bots = ['aggressive', 'conservative', 'custom']
                if bot_type not in valid_bots:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': f'Invalid bot_type. Must be one of: {", ".join(valid_bots)}'
                    }).encode())
                    return
                
                from db import set_active_bot, get_open_signal
                
                open_signal = get_open_signal()
                if open_signal:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'error': f'Cannot switch bot while signal #{open_signal["id"]} is still open. Wait for it to close first.'
                    }).encode())
                    return
                
                success = set_active_bot(bot_type)
                
                if success:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'active_bot': bot_type,
                        'message': f'Switched to {bot_type} strategy'
                    }).encode())
                else:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Failed to update bot type'}).encode())
                    
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
            except Exception as e:
                print(f"[SIGNAL BOT] Error setting active bot: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/upload-overlay':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            if not OBJECT_STORAGE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Object storage not available'}).encode())
                return
            
            try:
                content_type = self.headers['Content-Type']
                if not content_type.startswith('multipart/form-data'):
                    raise ValueError('Expected multipart/form-data')
                
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        'REQUEST_METHOD': 'POST',
                        'CONTENT_TYPE': self.headers['Content-Type'],
                    }
                )
                
                if 'overlayImage' not in form or not form['overlayImage'].filename:
                    raise ValueError('No overlay image provided')
                
                overlay_file = form['overlayImage']
                filename = overlay_file.filename
                
                # Generate unique filename with timestamp
                import time
                timestamp = int(time.time())
                ext = filename.split('.')[-1] if '.' in filename else 'png'
                overlay_filename = f"overlay_{timestamp}.{ext}"
                
                # Read image data
                image_data = overlay_file.file.read()
                
                # Upload to Spaces
                storage_service = ObjectStorageService()
                overlay_url = storage_service.upload_file(
                    image_data,
                    f'campaigns/overlays/{overlay_filename}'
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'overlay_url': overlay_url
                }).encode())
                
            except Exception as e:
                print(f"[OVERLAY] Upload error: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/upload-template':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_type = self.headers['Content-Type']
                if not content_type.startswith('multipart/form-data'):
                    raise ValueError('Expected multipart/form-data')
                
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        'REQUEST_METHOD': 'POST',
                        'CONTENT_TYPE': self.headers['Content-Type'],
                    }
                )
                
                name = form.getvalue('name')
                slug = form.getvalue('slug')
                name = form.getvalue('name')
                
                # DEBUG LOGGING
                print(f"[UPLOAD DEBUG] Received slug from client: '{slug}'")
                print(f"[UPLOAD DEBUG] Received name from client: '{name}'")
                
                import re
                if not slug or not re.match(r'^[a-z0-9-]+$', slug):
                    raise ValueError('Invalid slug: must contain only lowercase letters, numbers, and hyphens')
                
                if '..' in slug or '/' in slug or '\\' in slug:
                    raise ValueError('Invalid slug: path traversal detected')
                
                # Check if this is an edit or new upload
                is_editing = form.getvalue('isEditing') == 'true'
                print(f"[UPLOAD] isEditing flag: {is_editing}")
                
                # Check if template already exists (editing vs creating)
                template_dir = os.path.join('assets', 'templates', slug)
                is_existing_template = os.path.exists(template_dir)
                
                # Also check if template exists in Spaces via HTTP (for ephemeral environments)
                if not is_existing_template and OBJECT_STORAGE_AVAILABLE:
                    try:
                        import urllib.request
                        spaces_bucket = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
                        spaces_region = os.environ.get('SPACES_REGION', 'lon1')
                        cdn_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
                        req = urllib.request.Request(cdn_url, method='HEAD')
                        urllib.request.urlopen(req, timeout=5)
                        is_existing_template = True
                        print(f"[UPLOAD] Template '{slug}' exists in Spaces - allowing edit without images")
                    except urllib.error.HTTPError as e:
                        # 404 = doesn't exist (allow upload). Other errors = uncertain, allow upload to proceed
                        if e.code == 404:
                            print(f"[UPLOAD] Template '{slug}' confirmed not in Spaces (404) - allowing upload")
                        else:
                            # For 403, 500, etc - we can't confirm, but don't block legitimate uploads
                            print(f"[UPLOAD] Template '{slug}' - Spaces check got HTTP {e.code}, allowing upload to proceed")
                    except Exception as e:
                        print(f"[UPLOAD] Warning: Spaces check error for '{slug}': {e} - allowing upload to proceed")
                
                # SLUG CONFLICT VALIDATION: Prevent accidental overwrites
                if not is_editing and is_existing_template:
                    error_msg = f"Template with slug '{slug}' already exists! Click 'New Template' to clear the form or edit the existing template instead."
                    print(f"[UPLOAD] REJECTED: {error_msg}")
                    raise ValueError(error_msg)
                
                # Check if images are provided (optional for updates, at least one required for new templates)
                has_square_image = 'squareImage' in form and form['squareImage'].filename
                has_story_image = 'storyImage' in form and form['storyImage'].filename
                
                # For new templates, at least one image is required
                if not is_existing_template:
                    if not has_square_image and not has_story_image:
                        raise ValueError('At least one variant (square or portrait) image is required for new templates')
                
                square_coords = {
                    'leftPct': float(form.getvalue('squareLeftPct')),
                    'topPct': float(form.getvalue('squareTopPct')),
                    'widthPct': float(form.getvalue('squareWidthPct')),
                    'heightPct': float(form.getvalue('squareHeightPct')),
                    'hAlign': form.getvalue('squareHAlign'),
                    'vAlign': form.getvalue('squareVAlign')
                }
                
                story_coords = {
                    'leftPct': float(form.getvalue('storyLeftPct')),
                    'topPct': float(form.getvalue('storyTopPct')),
                    'widthPct': float(form.getvalue('storyWidthPct')),
                    'heightPct': float(form.getvalue('storyHeightPct')),
                    'hAlign': form.getvalue('storyHAlign'),
                    'vAlign': form.getvalue('storyVAlign')
                }
                
                square_max_font = int(float(form.getvalue('squareMaxFontPx')))
                story_max_font = int(float(form.getvalue('storyMaxFontPx')))
                
                # Get font colors with defaults
                square_font_color = form.getvalue('squareFontColor') or '#FF273E'
                story_font_color = form.getvalue('storyFontColor') or '#FF273E'
                
                # Check if object storage is available (only on Replit)
                if not OBJECT_STORAGE_AVAILABLE and (has_square_image or has_story_image):
                    raise ValueError('Template uploads are only available on Replit. Please use the Replit admin panel to upload templates.')
                
                # Initialize object storage service (only if available)
                storage_service = ObjectStorageService() if OBJECT_STORAGE_AVAILABLE else None
                image_urls = {}
                
                # Load existing meta.json to preserve all variant data if updating
                # Support both 'imageUrl' (new) and 'image' (legacy) fields
                existing_square_url = None
                existing_story_url = None
                existing_square_data = None
                existing_story_data = None
                existing_meta = None  # Initialize for both new and existing templates
                if is_existing_template:
                    meta_path = os.path.join(template_dir, 'meta.json')
                    
                    # Try loading from local filesystem first
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r') as f:
                                existing_meta = json.load(f)
                        except Exception as e:
                            print(f"Warning: Could not load local meta.json: {e}")
                    
                    # If not found locally, try downloading from Spaces
                    if not existing_meta and OBJECT_STORAGE_AVAILABLE:
                        try:
                            import urllib.request
                            spaces_bucket = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
                            spaces_region = os.environ.get('SPACES_REGION', 'lon1')
                            meta_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
                            response = urllib.request.urlopen(meta_url, timeout=5)
                            existing_meta = json.loads(response.read().decode('utf-8'))
                            print(f"[UPLOAD] Loaded existing meta.json from Spaces for '{slug}'")
                        except Exception as e:
                            print(f"Warning: Could not load meta.json from Spaces: {e}")
                    
                    # Parse existing metadata if found
                    if existing_meta:
                        if 'square' in existing_meta and isinstance(existing_meta['square'], dict):
                            existing_square_data = existing_meta['square']
                            # Check both new (imageUrl) and legacy (image) fields
                            existing_square_url = existing_square_data.get('imageUrl') or existing_square_data.get('image')
                        if 'story' in existing_meta and isinstance(existing_meta['story'], dict):
                            existing_story_data = existing_meta['story']
                            # Check both new (imageUrl) and legacy (image) fields  
                            existing_story_url = existing_story_data.get('imageUrl') or existing_story_data.get('image')
                
                # Upload images to object storage if provided and available
                if has_square_image and storage_service:
                    square_image = form['squareImage']
                    square_data = square_image.file.read()
                    image_urls['square'] = storage_service.upload_file(square_data, f"templates/{slug}/square.png")
                
                if has_story_image and storage_service:
                    story_image = form['storyImage']
                    story_data = story_image.file.read()
                    image_urls['story'] = storage_service.upload_file(story_data, f"templates/{slug}/story.png")
                
                # Create directory for meta.json (keep this local for now)
                os.makedirs(template_dir, exist_ok=True)
                
                # Determine imageUrl: use newly uploaded URL, or preserve existing, or None if not provided
                square_image_url = image_urls.get('square') or existing_square_url
                story_image_url = image_urls.get('story') or existing_story_url
                
                # Build meta.json with object storage URLs for images (only include variants that exist)
                # Preserve telegramEnabled from existing template, default to true for new templates
                existing_telegram_enabled = existing_meta.get('telegramEnabled', True) if existing_meta else True
                
                meta = {
                    'name': name,
                    'telegramEnabled': existing_telegram_enabled
                }
                
                # Add square variant if: newly uploaded, existing URL found, or existing variant data exists
                if square_image_url or has_square_image or existing_square_data:
                    # Build fresh variant dict - never mutate existing_square_data
                    meta['square'] = {
                        'box': square_coords,
                        'maxFontPx': square_max_font,
                        'fontColor': square_font_color,
                        'imageUrl': square_image_url or existing_square_url or f'assets/templates/{slug}/square.png'
                    }
                
                # Add story variant if: newly uploaded, existing URL found, or existing variant data exists
                if story_image_url or has_story_image or existing_story_data:
                    # Build fresh variant dict - never mutate existing_story_data
                    meta['story'] = {
                        'box': story_coords,
                        'maxFontPx': story_max_font,
                        'fontColor': story_font_color,
                        'imageUrl': story_image_url or existing_story_url or f'assets/templates/{slug}/story.png'
                    }
                
                # Validation: ensure at least one variant exists in final meta
                if 'square' not in meta and 'story' not in meta:
                    raise ValueError('Template must have at least one variant (square or portrait)')
                
                # Save meta.json locally
                meta_path = os.path.join(template_dir, 'meta.json')
                with open(meta_path, 'w') as f:
                    json.dump(meta, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Also save meta.json to object storage for persistence (if available)
                if storage_service:
                    meta_json_str = json.dumps(meta, indent=2)
                    storage_service.upload_file(meta_json_str.encode(), f"templates/{slug}/meta.json")
                
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise Exception(f'Index regeneration failed: {result.stderr or result.stdout}')
                
                # CRITICAL: Upload index.json to Spaces so it persists across deployments
                if storage_service:
                    index_path = os.path.join('assets', 'templates', 'index.json')
                    if os.path.exists(index_path):
                        with open(index_path, 'r') as f:
                            index_content = f.read()
                        storage_service.upload_file(index_content.encode(), 'templates/index.json')
                        print(f"[UPLOAD] index.json uploaded to Spaces for persistence")
                
                # Clear Telegram bot cache so new template is available immediately
                if TELEGRAM_BOT_AVAILABLE:
                    telegram_bot.INDEX_CACHE['data'] = None
                    telegram_bot.INDEX_CACHE['expires_at'] = 0
                    print(f"[UPLOAD] Telegram cache cleared - template available immediately")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Template "{name}" uploaded successfully',
                    'slug': slug
                }).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/delete-template':
            print(f"[DELETE] Delete request received")
            if not self.check_auth():
                print(f"[DELETE] Authentication failed - returning 401")
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - please login again'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                slug = data.get('slug', '')
                
                print(f"[DELETE] Authenticated - attempting to delete template: {slug}")
                
                import re
                if not slug or not re.match(r'^[a-z0-9-]+$', slug):
                    raise ValueError('Invalid slug')
                
                if '..' in slug or '/' in slug or '\\' in slug:
                    raise ValueError('Invalid slug: path traversal detected')
                
                template_dir = os.path.join('assets', 'templates', slug)
                deleted_something = False
                
                # Delete from object storage first (if available) - this is the primary source
                if OBJECT_STORAGE_AVAILABLE:
                    storage_service = ObjectStorageService()
                    storage_service.delete_template(slug)
                    print(f"[DELETE] Template removed from object storage: {slug}")
                    deleted_something = True
                
                # Delete local directory if it exists (optional - may not exist in production)
                import shutil
                if os.path.exists(template_dir):
                    shutil.rmtree(template_dir)
                    print(f"[DELETE] Template directory removed: {template_dir}")
                    deleted_something = True
                else:
                    print(f"[DELETE] No local directory found (normal in production): {template_dir}")
                
                # Make sure we deleted something
                if not deleted_something:
                    raise ValueError(f'Template "{slug}" not found in storage or locally')
                
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise Exception(f'Index regeneration failed: {result.stderr or result.stdout}')
                
                print(f"[DELETE] Index regenerated successfully")
                
                # CRITICAL: Upload index.json to Spaces so deletion persists across deployments
                if OBJECT_STORAGE_AVAILABLE:
                    index_path = os.path.join('assets', 'templates', 'index.json')
                    if os.path.exists(index_path):
                        with open(index_path, 'r') as f:
                            index_content = f.read()
                        storage_service.upload_file(index_content.encode(), 'templates/index.json')
                        print(f"[DELETE] index.json uploaded to Spaces after deletion")
                
                # Clear Telegram bot cache so deletion is reflected immediately
                if TELEGRAM_BOT_AVAILABLE:
                    telegram_bot.INDEX_CACHE['data'] = None
                    telegram_bot.INDEX_CACHE['expires_at'] = 0
                    print(f"[DELETE] Telegram cache cleared - template removed immediately")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Template "{slug}" deleted successfully'
                }).encode())
                
                print(f"[DELETE] Success response sent for: {slug}")
                
            except Exception as e:
                print(f"[DELETE] Error during deletion: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/toggle-telegram-template':
            # Verify admin authentication
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                slug = data.get('slug')
                enabled = data.get('enabled', True)
                
                if not slug:
                    raise ValueError('Template slug is required')
                
                print(f"[TELEGRAM_TOGGLE] Toggling template '{slug}' to {'enabled' if enabled else 'disabled'}")
                
                # Download existing meta.json from Spaces
                import urllib.request
                spaces_bucket = os.environ.get('SPACES_BUCKET', 'couponpro-templates')
                spaces_region = os.environ.get('SPACES_REGION', 'lon1')
                meta_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
                
                try:
                    response = urllib.request.urlopen(meta_url, timeout=5)
                    meta = json.loads(response.read().decode('utf-8'))
                except Exception as e:
                    raise ValueError(f'Could not load template metadata: {e}')
                
                # Update telegramEnabled flag
                meta['telegramEnabled'] = enabled
                
                # Save back to Spaces
                if OBJECT_STORAGE_AVAILABLE:
                    storage_service = ObjectStorageService()
                    meta_json_str = json.dumps(meta, indent=2)
                    storage_service.upload_file(meta_json_str.encode(), f"templates/{slug}/meta.json")
                    print(f"[TELEGRAM_TOGGLE] Updated meta.json for '{slug}' in Spaces")
                
                # Also save locally if directory exists
                template_dir = os.path.join('assets', 'templates', slug)
                if os.path.exists(template_dir):
                    meta_path = os.path.join(template_dir, 'meta.json')
                    with open(meta_path, 'w') as f:
                        json.dump(meta, f, indent=2)
                
                # Regenerate index.json to reflect changes in Telegram bot
                try:
                    result = subprocess.run(
                        ['python3', 'regenerate_index.py'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        print(f"[TELEGRAM_TOGGLE] Warning: Index regeneration failed: {result.stderr}")
                    else:
                        print(f"[TELEGRAM_TOGGLE] Index regenerated successfully")
                        
                        # Upload updated index.json to Spaces
                        if storage_service:
                            index_path = os.path.join('assets', 'templates', 'index.json')
                            if os.path.exists(index_path):
                                with open(index_path, 'r') as f:
                                    index_content = f.read()
                                storage_service.upload_file(index_content.encode(), 'templates/index.json')
                                print(f"[TELEGRAM_TOGGLE] Index.json uploaded to Spaces")
                except Exception as e:
                    print(f"[TELEGRAM_TOGGLE] Warning: Index update failed: {e}")
                
                # Clear Telegram bot cache so visibility change is reflected immediately
                if TELEGRAM_BOT_AVAILABLE:
                    telegram_bot.INDEX_CACHE['data'] = None
                    telegram_bot.INDEX_CACHE['expires_at'] = 0
                    print(f"[TELEGRAM_TOGGLE] Telegram cache cleared - visibility change applied immediately")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f"Template '{slug}' {'enabled' if enabled else 'disabled'} for Telegram"
                }).encode())
                
            except Exception as e:
                print(f"[TELEGRAM_TOGGLE] Error: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/clear-telegram-cache':
            # Clear Telegram bot's template cache (requires admin auth)
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                if TELEGRAM_BOT_AVAILABLE:
                    # Clear the INDEX_CACHE in telegram_bot module
                    telegram_bot.INDEX_CACHE['data'] = None
                    telegram_bot.INDEX_CACHE['expires_at'] = 0
                    print(f"[CACHE] Telegram template cache cleared")
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'message': 'Telegram cache cleared - new templates available immediately'
                    }).encode())
                else:
                    self.send_response(503)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'error': 'Telegram bot not available'
                    }).encode())
                    
            except Exception as e:
                print(f"[CACHE] Error clearing cache: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/regenerate-index':
            try:
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'success': True,
                        'message': 'Index regenerated successfully',
                        'output': result.stdout
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'success': False,
                        'error': result.stderr or 'Failed to regenerate index'
                    }
                    self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
        
        elif parsed_path.path == '/api/telegram-webhook':
            import sys
            import time
            start_time = time.time()
            print(f"[WEBHOOK-ENDPOINT] ⚡ Webhook endpoint called!", flush=True)
            sys.stdout.flush()
            
            if not TELEGRAM_BOT_AVAILABLE:
                print(f"[WEBHOOK-ENDPOINT] ❌ Bot not available", flush=True)
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Telegram bot not available'}).encode())
                return
            
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                print(f"[WEBHOOK-ENDPOINT] Received {content_length} bytes", flush=True)
                bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
                
                if not bot_token:
                    print(f"[WEBHOOK-ENDPOINT] ❌ Bot token not configured", flush=True)
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Bot token not configured'}).encode())
                    return
                
                # Parse JSON from webhook
                webhook_data = json.loads(post_data.decode('utf-8'))
                update_id = webhook_data.get('update_id', 'unknown')
                print(f"[WEBHOOK-ENDPOINT] Processing update_id: {update_id}", flush=True)
                
                # Handle the webhook (tracking happens inside bot handlers)
                result = telegram_bot.handle_telegram_webhook(webhook_data, bot_token)
                
                elapsed = time.time() - start_time
                print(f"[WEBHOOK-ENDPOINT] ✅ Completed update_id {update_id} in {elapsed:.2f}s, result: {result}", flush=True)
                sys.stdout.flush()
                
                # Telegram expects 200 OK even if we couldn't process the command
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"[WEBHOOK-ENDPOINT] ❌ Webhook error after {elapsed:.2f}s: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
                # Still send 200 to Telegram so it doesn't retry
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/forex-telegram-webhook':
            import sys
            import time
            start_time = time.time()
            print(f"[FOREX-WEBHOOK] ⚡ Forex webhook endpoint called!", flush=True)
            sys.stdout.flush()
            
            if not TELEGRAM_BOT_AVAILABLE:
                print(f"[FOREX-WEBHOOK] ❌ Telegram bot module not available", flush=True)
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Telegram bot not available'}).encode())
                return
            
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                
                # Use appropriate bot token based on environment
                from forex_bot import get_forex_bot_token
                forex_bot_token = get_forex_bot_token()
                
                if not forex_bot_token:
                    print(f"[FOREX-WEBHOOK] ❌ Forex bot token not configured", flush=True)
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Forex bot token not configured'}).encode())
                    return
                
                webhook_data = json.loads(post_data.decode('utf-8'))
                update_id = webhook_data.get('update_id', 'unknown')
                print(f"[FOREX-WEBHOOK] Processing update_id: {update_id}", flush=True)
                
                result = telegram_bot.handle_forex_webhook(webhook_data, forex_bot_token)
                
                elapsed = time.time() - start_time
                print(f"[FOREX-WEBHOOK] ✅ Completed update_id {update_id} in {elapsed:.2f}s, result: {result}", flush=True)
                sys.stdout.flush()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"[FOREX-WEBHOOK] ❌ Webhook error after {elapsed:.2f}s: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/grant-access':
            # EntryLab API - Grant access to private Telegram channel
            api_key = self.headers.get('X-API-Key') or self.headers.get('Authorization', '').replace('Bearer ', '')
            expected_key = os.environ.get('ENTRYLAB_API_KEY', '')
            
            if not api_key or api_key != expected_key or not expected_key:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - Invalid API key'}).encode())
                return
            
            if not TELEGRAM_BOT_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Telegram bot not available'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                email = data.get('email')
                
                # Normalize Stripe fields - treat placeholders as None for clean data
                stripe_placeholders = {'', 'free', 'free_signup', 'test', 'null', 'none', 'n/a'}
                raw_customer_id = data.get('stripeCustomerId')
                raw_subscription_id = data.get('stripeSubscriptionId')
                stripe_customer_id = None if not raw_customer_id or str(raw_customer_id).lower().strip() in stripe_placeholders else raw_customer_id
                stripe_subscription_id = None if not raw_subscription_id or str(raw_subscription_id).lower().strip() in stripe_placeholders else raw_subscription_id
                user_id = data.get('userId')
                name = data.get('name')
                plan_type = data.get('planType', 'premium')
                
                # UTM tracking parameters for marketing attribution
                utm_source = data.get('utmSource') or data.get('utm_source')
                utm_medium = data.get('utmMedium') or data.get('utm_medium')
                utm_campaign = data.get('utmCampaign') or data.get('utm_campaign')
                utm_content = data.get('utmContent') or data.get('utm_content')
                utm_term = data.get('utmTerm') or data.get('utm_term')
                
                # Smart default for amount: Free plans default to 0, Premium defaults to 49
                raw_amount = data.get('amountPaid')
                if raw_amount is not None:
                    amount_paid = float(raw_amount)
                elif 'free' in plan_type.lower():
                    amount_paid = 0.0
                else:
                    amount_paid = 49.00
                
                if not email:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing required field: email'}).encode())
                    return
                
                is_free_user = amount_paid == 0 or 'free' in plan_type.lower()
                print(f"[TELEGRAM-SUB] Grant access request for {email}")
                print(f"[TELEGRAM-SUB] Data: plan={plan_type}, amount=${amount_paid}, free={is_free_user}")
                print(f"[TELEGRAM-SUB] Stripe: customer_id={stripe_customer_id}, subscription_id={stripe_subscription_id}")
                if utm_source or utm_campaign:
                    print(f"[TELEGRAM-SUB] UTM: source={utm_source}, medium={utm_medium}, campaign={utm_campaign}")
                
                # Create subscription record in database (with UTM tracking for conversions)
                subscription, db_error = db.create_telegram_subscription(
                    email=email,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    plan_type=plan_type,
                    amount_paid=amount_paid,
                    name=name,
                    utm_source=utm_source,
                    utm_medium=utm_medium,
                    utm_campaign=utm_campaign,
                    utm_content=utm_content,
                    utm_term=utm_term
                )
                
                if not subscription:
                    error_msg = db_error or 'Failed to create subscription record'
                    print(f"[TELEGRAM-SUB] ❌ Database error: {error_msg}")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': error_msg}).encode())
                    return
                
                # FREE USERS: Just record the lead, no private invite link needed
                # They will be given the public channel link by EntryLab
                if is_free_user:
                    print(f"[TELEGRAM-SUB] ✅ Free lead captured for {email}")
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'inviteLink': None,
                        'message': 'Free lead captured successfully',
                        'isFreeUser': True
                    }).encode())
                    return
                
                # PREMIUM USERS: Generate unique invite link for private channel
                private_channel_id = os.environ.get('FOREX_CHANNEL_ID')
                if not private_channel_id:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'FOREX_CHANNEL_ID not configured'}).encode())
                    return
                
                invite_link = telegram_bot.sync_create_private_channel_invite_link(private_channel_id)
                
                if not invite_link:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Failed to create invite link'}).encode())
                    return
                
                # Update subscription with invite link
                db.update_telegram_subscription_invite(email, invite_link)
                
                print(f"[TELEGRAM-SUB] ✅ Premium access granted for {email}, invite: {invite_link}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'inviteLink': invite_link,
                    'message': 'Premium access granted successfully',
                    'isFreeUser': False
                }).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
            except Exception as e:
                print(f"[TELEGRAM-SUB] Error granting access: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/clear-all':
            # Admin API - Clear all telegram subscriptions (for testing)
            api_key = self.headers.get('X-API-Key') or self.headers.get('Authorization', '').replace('Bearer ', '')
            expected_key = os.environ.get('ENTRYLAB_API_KEY', '')
            
            if not api_key or api_key != expected_key or not expected_key:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                deleted = db.clear_all_telegram_subscriptions()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Cleared {deleted} subscription records'
                }).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/cleanup-test-data':
            # Admin API - Delete test subscription records (fake paid data)
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                # Use db function to cleanup test records
                deleted_info = db.cleanup_test_telegram_subscriptions()
                
                print(f"[CLEANUP] Deleted {len(deleted_info)} test records: {deleted_info}")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Deleted {len(deleted_info)} test records',
                    'deleted': deleted_info
                }).encode())
                
            except Exception as e:
                print(f"[CLEANUP] Error: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/cancel-subscription':
            # Admin API - Cancel a Stripe subscription
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                subscription_id = data.get('subscriptionId')
                cancel_immediately = data.get('cancelImmediately', False)
                
                if not subscription_id:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing subscriptionId'}).encode())
                    return
                
                # Get subscription from our database
                subscription = db.get_telegram_subscription_by_id(int(subscription_id))
                
                if not subscription:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Subscription not found'}).encode())
                    return
                
                stripe_subscription_id = subscription.get('stripe_subscription_id')
                
                if not stripe_subscription_id:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'No Stripe subscription linked to this record'}).encode())
                    return
                
                print(f"[CANCEL] Canceling subscription {stripe_subscription_id} for user {subscription.get('email')}, immediately={cancel_immediately}")
                
                # Cancel in Stripe
                from stripe_client import cancel_subscription
                result = cancel_subscription(stripe_subscription_id, cancel_immediately=cancel_immediately)
                
                if result.get('success'):
                    # If canceled immediately, also revoke access and kick from Telegram
                    kicked_from_telegram = False
                    if cancel_immediately:
                        telegram_user_id = db.revoke_telegram_subscription(subscription.get('email'), 'admin_canceled')
                        
                        # Kick user from Telegram channel if they have joined
                        if telegram_user_id and TELEGRAM_BOT_AVAILABLE:
                            private_channel_id = os.environ.get('FOREX_CHANNEL_ID')
                            if private_channel_id:
                                from telegram_bot import sync_kick_user_from_channel
                                kicked_from_telegram = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                                if kicked_from_telegram:
                                    print(f"[CANCEL] Kicked user {telegram_user_id} from Telegram channel")
                                else:
                                    print(f"[CANCEL] Warning: Failed to kick user {telegram_user_id} from Telegram channel")
                        
                        result['kicked_from_telegram'] = kicked_from_telegram
                        result['message'] = 'Subscription canceled immediately' + (' and removed from Telegram channel' if kicked_from_telegram else '')
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                    
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
            except Exception as e:
                print(f"[CANCEL] Error canceling subscription: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/delete-subscription':
            # Admin API - Delete a subscription record from the database
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                subscription_id = data.get('subscriptionId')
                telegram_user_id = data.get('telegramUserId')
                
                if not subscription_id:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing subscriptionId'}).encode())
                    return
                
                # Get subscription first to log what we're deleting
                subscription = db.get_telegram_subscription_by_id(int(subscription_id))
                if subscription:
                    print(f"[DELETE] Deleting subscription record: ID={subscription_id}, Email={subscription.get('email')}")
                
                # Kick from Telegram if they have a telegram_user_id
                kicked = False
                if telegram_user_id and TELEGRAM_BOT_AVAILABLE:
                    private_channel_id = os.environ.get('FOREX_CHANNEL_ID')
                    if private_channel_id:
                        from telegram_bot import sync_kick_user_from_channel
                        kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                        if kicked:
                            print(f"[DELETE] Kicked user {telegram_user_id} from Telegram channel")
                
                # Delete from database
                deleted = db.delete_telegram_subscription(int(subscription_id))
                
                if deleted:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'message': 'Subscription deleted successfully',
                        'kicked_from_telegram': kicked
                    }).encode())
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Subscription not found or already deleted'}).encode())
                    
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
            except Exception as e:
                print(f"[DELETE] Error deleting subscription: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/telegram/revoke-access':
            # EntryLab API - Revoke access to private Telegram channel
            api_key = self.headers.get('X-API-Key') or self.headers.get('Authorization', '').replace('Bearer ', '')
            expected_key = os.environ.get('ENTRYLAB_API_KEY', '')
            
            if not api_key or api_key != expected_key or not expected_key:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - Invalid API key'}).encode())
                return
            
            if not TELEGRAM_BOT_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Telegram bot not available'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                email = data.get('email')
                reason = data.get('reason', 'subscription_canceled')
                
                if not email:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing required field: email'}).encode())
                    return
                
                print(f"[TELEGRAM-SUB] Revoke access request for {email}, reason: {reason}")
                
                # Get subscription to find Telegram user ID
                subscription = db.get_telegram_subscription_by_email(email)
                
                if not subscription:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': f'No subscription found for {email}'}).encode())
                    return
                
                # Revoke in database
                telegram_user_id = db.revoke_telegram_subscription(email, reason)
                
                # Kick user from channel if they've joined
                if telegram_user_id:
                    private_channel_id = os.environ.get('FOREX_CHANNEL_ID')
                    if not private_channel_id:
                        print("[TELEGRAM-SUB] ⚠️ FOREX_CHANNEL_ID not configured, cannot kick user")
                    else:
                        kicked = telegram_bot.sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                        
                        if kicked:
                            print(f"[TELEGRAM-SUB] ✅ User {telegram_user_id} kicked from channel")
                        else:
                            print(f"[TELEGRAM-SUB] ⚠️  Failed to kick user {telegram_user_id}")
                
                # TODO: Send cancellation email (when Resend is set up)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Access revoked for {email}'
                }).encode())
                
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
            except Exception as e:
                print(f"[TELEGRAM-SUB] Error revoking access: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/stripe/webhook':
            # Stripe Webhook - Handle subscription events automatically
            # No auth required - uses Stripe signature verification
            try:
                content_length = int(self.headers['Content-Length'])
                payload = self.rfile.read(content_length)
                sig_header = self.headers.get('Stripe-Signature')
                
                webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
                
                if not STRIPE_AVAILABLE:
                    print("[STRIPE WEBHOOK] Stripe not available")
                    self.send_response(503)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Stripe not available'}).encode())
                    return
                
                from stripe_client import verify_webhook_signature, get_subscription_details
                
                # If webhook secret is configured, verify signature
                if webhook_secret and sig_header:
                    event, error = verify_webhook_signature(payload, sig_header, webhook_secret)
                    if error:
                        print(f"[STRIPE WEBHOOK] Signature verification failed: {error}")
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'error': error}).encode())
                        return
                else:
                    # No webhook secret - parse event directly (less secure, for development)
                    try:
                        event = json.loads(payload.decode('utf-8'))
                        print(f"[STRIPE WEBHOOK] Warning: No webhook secret configured, skipping signature verification")
                    except json.JSONDecodeError as e:
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
                        return
                
                event_type = event.get('type') if isinstance(event, dict) else event.type
                event_id = event.get('id') if isinstance(event, dict) else event.id
                event_data = event.get('data', {}).get('object', {}) if isinstance(event, dict) else event.data.object
                
                print(f"[STRIPE WEBHOOK] Received event: {event_type} ({event_id})")
                
                # Idempotency check - skip if we've already processed this event
                if event_id and db.is_webhook_event_processed(event_id):
                    print(f"[STRIPE WEBHOOK] ⏭️ Event {event_id} already processed, skipping")
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'received': True, 'duplicate': True}).encode())
                    return
                
                # Handle different event types
                if event_type == 'checkout.session.completed':
                    # New subscription payment completed
                    subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
                    customer_id = event_data.get('customer') if isinstance(event_data, dict) else getattr(event_data, 'customer', None)
                    customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
                    amount_total = (event_data.get('amount_total') if isinstance(event_data, dict) else getattr(event_data, 'amount_total', 0)) or 0
                    
                    if subscription_id:
                        # Get full subscription details from Stripe
                        sub_details = get_subscription_details(subscription_id)
                        
                        if sub_details:
                            email = sub_details.get('email') or customer_email
                            name = sub_details.get('name')
                            amount_paid = sub_details.get('amount_paid') or (amount_total / 100)
                            plan_name = sub_details.get('plan_name') or 'premium'
                            
                            print(f"[STRIPE WEBHOOK] Creating subscription: email={email}, sub_id={subscription_id}, amount=${amount_paid}")
                            
                            # Create or update subscription in database
                            result, error = db.create_or_update_telegram_subscription(
                                email=email,
                                stripe_customer_id=customer_id,
                                stripe_subscription_id=subscription_id,
                                plan_type=plan_name,
                                amount_paid=amount_paid,
                                name=name
                            )
                            
                            if result:
                                print(f"[STRIPE WEBHOOK] ✅ Subscription created/updated: {email}")
                            else:
                                print(f"[STRIPE WEBHOOK] ❌ Failed to create subscription: {error}")
                        else:
                            print(f"[STRIPE WEBHOOK] Could not fetch subscription details for {subscription_id}")
                    else:
                        print(f"[STRIPE WEBHOOK] checkout.session.completed without subscription_id (one-time payment?)")
                
                elif event_type == 'customer.subscription.created':
                    # Subscription created
                    subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
                    
                    sub_details = get_subscription_details(subscription_id)
                    if sub_details and sub_details.get('email'):
                        result, error = db.create_or_update_telegram_subscription(
                            email=sub_details['email'],
                            stripe_customer_id=sub_details.get('customer_id'),
                            stripe_subscription_id=subscription_id,
                            plan_type=sub_details.get('plan_name') or 'premium',
                            amount_paid=sub_details.get('amount_paid', 0),
                            name=sub_details.get('name')
                        )
                        print(f"[STRIPE WEBHOOK] customer.subscription.created: {sub_details['email']} - {'success' if result else error}")
                
                elif event_type == 'customer.subscription.updated':
                    # Subscription updated (e.g., plan change, cancellation scheduled)
                    subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
                    cancel_at_period_end = event_data.get('cancel_at_period_end') if isinstance(event_data, dict) else getattr(event_data, 'cancel_at_period_end', False)
                    status = event_data.get('status') if isinstance(event_data, dict) else event_data.status
                    
                    print(f"[STRIPE WEBHOOK] customer.subscription.updated: {subscription_id}, status={status}, cancel_at_period_end={cancel_at_period_end}")
                    
                    # Update subscription status in database if needed
                    sub_details = get_subscription_details(subscription_id)
                    if sub_details and sub_details.get('email'):
                        # Just log for now - could update status in DB
                        print(f"[STRIPE WEBHOOK] Subscription {subscription_id} updated for {sub_details['email']}")
                
                elif event_type == 'customer.subscription.deleted':
                    # Subscription canceled/ended
                    subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
                    print(f"[STRIPE WEBHOOK] customer.subscription.deleted: {subscription_id}")
                    
                    sub_details = get_subscription_details(subscription_id)
                    if sub_details and sub_details.get('email'):
                        # Revoke access in database
                        telegram_user_id = db.revoke_telegram_subscription(sub_details['email'], 'subscription_canceled')
                        print(f"[STRIPE WEBHOOK] Revoked access for {sub_details['email']}")
                        
                        # Kick from Telegram if configured
                        if telegram_user_id and TELEGRAM_BOT_AVAILABLE:
                            private_channel_id = os.environ.get('FOREX_CHANNEL_ID')
                            if private_channel_id:
                                from telegram_bot import sync_kick_user_from_channel
                                kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                                print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id}: {kicked}")
                
                elif event_type == 'invoice.paid':
                    # Invoice paid - update amount_paid for renewals
                    subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
                    amount_paid = (event_data.get('amount_paid') if isinstance(event_data, dict) else getattr(event_data, 'amount_paid', 0)) or 0
                    customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
                    
                    if subscription_id and amount_paid > 0:
                        print(f"[STRIPE WEBHOOK] invoice.paid: {subscription_id}, amount=${amount_paid/100}, email={customer_email}")
                
                # Record this event as processed to prevent duplicate handling
                if event_id:
                    db.record_webhook_event_processed(event_id, event_type)
                    print(f"[STRIPE WEBHOOK] ✅ Event {event_id} recorded as processed")
                
                # Periodically cleanup old events (every ~100 requests)
                import random
                if random.random() < 0.01:  # 1% chance
                    db.cleanup_old_webhook_events(hours=24)
                
                # Always return 200 to acknowledge receipt
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'received': True}).encode())
                
            except Exception as e:
                # Return 500 for processing errors to allow Stripe retries
                # The idempotency table prevents duplicate processing on retry
                print(f"[STRIPE WEBHOOK] ❌ Error processing webhook: {e}")
                import traceback
                traceback.print_exc()
                # Return 500 so Stripe will retry (idempotency handles duplicates)
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
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
        
        elif parsed_path.path == '/api/campaigns':
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
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                campaign_id = db.create_campaign(
                    title=data['title'],
                    description=data.get('description', ''),
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    prize=data.get('prize', ''),
                    platforms=json.dumps(data.get('platforms', [])),
                    overlay_url=data.get('overlay_url')
                )
                
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'id': campaign_id}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error creating campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submit' in parsed_path.path:
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                submission_id = db.create_submission(
                    campaign_id=campaign_id,
                    email=data['email'],
                    instagram_url=data.get('instagram_url', ''),
                    twitter_url=data.get('twitter_url', ''),
                    facebook_url=data.get('facebook_url', '')
                )
                
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'id': submission_id}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error creating submission: {e}")
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
    # Initialize Telegram bot in webhook mode if token is available
    if TELEGRAM_BOT_AVAILABLE:
        try:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN_TEST')
            if bot_token:
                print("[TELEGRAM] Initializing bot for webhook mode...")
                telegram_bot.start_webhook_bot(bot_token)
        except Exception as e:
            print(f"[TELEGRAM] Failed to start bot: {e}")
            import traceback
            traceback.print_exc()
    
    # Set up forex bot webhook for join tracking (replaces polling to avoid conflicts)
    if TELEGRAM_BOT_AVAILABLE:
        from forex_bot import get_forex_bot_token
        forex_bot_token = get_forex_bot_token()
        if forex_bot_token:
            webhook_url = "https://dash.promostack.io/api/forex-telegram-webhook"
            try:
                success = telegram_bot.setup_forex_webhook(forex_bot_token, webhook_url)
                if success:
                    print("[JOIN_TRACKER] ✅ Webhook configured:", webhook_url)
                    print("[JOIN_TRACKER] ✅ Forex bot webhook mode initialized")
                else:
                    print("[JOIN_TRACKER] ⚠️ Failed to set up webhook, join tracking may not work")
            except Exception as e:
                print(f"[JOIN_TRACKER] ❌ Error setting up webhook: {e}")
        else:
            print("[JOIN_TRACKER] ⚠️ Forex bot token not set, join tracking disabled")
    
    # Start Forex signals scheduler in background thread if available
    if FOREX_SCHEDULER_AVAILABLE:
        import threading
        import asyncio
        
        def run_forex_scheduler():
            """Run the forex scheduler in a separate thread"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(start_forex_scheduler())
            except Exception as e:
                print(f"[FOREX] Scheduler error: {e}")
                import traceback
                traceback.print_exc()
        
        scheduler_thread = threading.Thread(target=run_forex_scheduler, daemon=True)
        scheduler_thread.start()
        print("[FOREX] Signals scheduler started in background thread")
    
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
