#!/usr/bin/env python3
"""Thin HTTP server - all request dispatching goes through api/dispatch.py"""
import http.server, socketserver, os, json, mimetypes, time
from urllib.parse import urlparse
from http import cookies
from dotenv import load_dotenv
load_dotenv()

from core.logging import get_logger, set_request_context, clear_request_context
logger = get_logger(__name__)
from core.config import Config
from core.host_context import parse_host_context, HostType
from api.routes import GET_ROUTES, POST_ROUTES, PUT_ROUTES, DELETE_ROUTES, PAGE_ROUTES, AUTH_ROUTES, ADMIN_ROUTES
from api.dispatch import dispatch_request
from domains.subscriptions import handlers as sub_h
from domains.coupons import handlers as coupon_h
from domains.forex import handlers as forex_h
from domains.tenant import handlers as tenant_h
from handlers import onboarding_handlers as onboard_h, stripe_products_handlers as stripe_h, pages
from integrations.telegram.webhooks import handle_coupon_telegram_webhook, handle_forex_telegram_webhook, handle_bot_webhook
from integrations.stripe.webhooks import handle_stripe_webhook

OBJECT_STORAGE_AVAILABLE = TELEGRAM_BOT_AVAILABLE = DATABASE_AVAILABLE = False
COUPON_VALIDATOR_AVAILABLE = FOREX_SCHEDULER_AVAILABLE = STRIPE_AVAILABLE = False
db = coupon_validator = telegram_bot = None

try:
    from object_storage import ObjectStorageService
    OBJECT_STORAGE_AVAILABLE = True
except: pass

PORT = Config.get_port()
DIRECTORY = "."
SESSION_TTL = 86400
mimetypes.add_type('text/yaml', '.yml')
mimetypes.add_type('text/yaml', '.yaml')
mimetypes.add_type('application/json', '.json')

from auth.clerk_auth import create_admin_session, verify_admin_session

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def _json(self, status, data):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def check_auth(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email
        u = get_auth_user_from_request(self, record_failure=False)
        if u:
            email = u.get('email') or self.headers.get('X-Clerk-User-Email')
            return is_admin_email(email)
        return False

    # Page handlers
    def handle_page_login(self): pages.serve_login(self)
    def handle_page_admin(self): pages.serve_admin(self, self.host_context)
    def handle_page_app(self): pages.serve_app(self, self.host_context)
    def handle_page_setup(self): pages.serve_setup(self)
    def handle_page_coupon(self): pages.serve_coupon(self)
    def handle_page_campaign(self): pages.serve_campaign(self)

    # Auth handlers
    def handle_auth_me(self):
        from auth.clerk_auth import require_auth
        try:
            u = require_auth(self)
            info = db.upsert_clerk_user(clerk_user_id=u['clerk_user_id'], email=u.get('email'), name=u.get('name'), avatar_url=u.get('avatar_url'))
            self._json(200, {'user': info})
        except Exception as e:
            self._json(getattr(e, 'status_code', 500), {'error': str(e)})

    def handle_auth_logout(self): self._json(200, {'success': True})

    # Admin
    def handle_api_admin_tenants(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email
        from handlers.admin_handlers import handle_get_tenants
        u = get_auth_user_from_request(self)
        if not u: return self._json(401, {'error': 'Authentication required'})
        if not is_admin_email(u.get('email') or self.headers.get('X-Clerk-User-Email', '')): return self._json(403, {'error': 'Admin access required'})
        handle_get_tenants(self)

    def handle_api_check_auth(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email
        u = get_auth_user_from_request(self, record_failure=False)
        if u:
            email = u.get('email') or self.headers.get('X-Clerk-User-Email')
            if is_admin_email(email):
                return self._json(200, {'authenticated': True, 'email': email, 'avatar': u.get('avatar_url')})
            else:
                return self._json(200, {'authenticated': False, 'email': email})
        self._json(200, {'authenticated': False})

    def handle_api_auth_debug(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email, get_jwks_status
        from auth.auth_debug import get_recent_failures, get_failure_count
        u = get_auth_user_from_request(self, record_failure=False)
        if not u:
            return self._json(401, {'error': 'Authentication required'})
        email = u.get('email') or self.headers.get('X-Clerk-User-Email', '')
        if not is_admin_email(email):
            return self._json(403, {'error': 'Admin access required'})
        failures = get_recent_failures(50)
        jwks_status = get_jwks_status()
        self._json(200, {
            'jwks': jwks_status,
            'failures': failures,
            'total_in_buffer': get_failure_count()
        })

    def handle_api_config(self):
        from urllib.parse import parse_qs
        qs = parse_qs(urlparse(self.path).query)
        host_type = qs.get('host_type', [self.host_context.host_type.value])[0] if hasattr(self, 'host_context') else 'default'
        self._json(200, {'clerkPublishableKey': Config.get_clerk_publishable_key(), 'hostType': host_type})

    # Coupon domain handlers
    def handle_api_campaigns(self): coupon_h.handle_campaigns_list(self)
    def handle_api_campaign_by_id(self): coupon_h.handle_campaign_by_id(self)
    def handle_api_campaign_submissions(self): coupon_h.handle_campaign_submissions(self)
    def handle_api_campaigns_create(self): coupon_h.handle_campaigns_create(self)
    def handle_api_campaign_submit(self): coupon_h.handle_campaign_submit(self)
    def handle_api_campaign_update(self): coupon_h.handle_campaign_update(self)
    def handle_api_campaign_delete(self): coupon_h.handle_campaign_delete(self)
    def handle_api_bot_stats(self): coupon_h.handle_bot_stats(self)
    def handle_api_day_of_week_stats(self): coupon_h.handle_day_of_week_stats(self)
    def handle_api_retention_rates(self): coupon_h.handle_retention_rates(self)
    def handle_api_bot_users(self): coupon_h.handle_bot_users(self)
    def handle_api_broadcast_status(self): coupon_h.handle_broadcast_status(self)
    def handle_api_broadcast_jobs(self): coupon_h.handle_broadcast_jobs(self)
    def handle_api_user_activity(self): coupon_h.handle_user_activity(self)
    def handle_api_invalid_coupons(self): coupon_h.handle_invalid_coupons(self)
    def handle_api_validate_coupon(self): coupon_h.handle_validate_coupon(self)
    def handle_api_broadcast(self): coupon_h.handle_broadcast(self)
    def handle_api_upload_overlay(self): coupon_h.handle_upload_overlay(self)
    def handle_api_upload_template(self): coupon_h.handle_upload_template(self)
    def handle_api_delete_template(self): coupon_h.handle_delete_template(self)
    def handle_api_toggle_telegram_template(self): coupon_h.handle_toggle_telegram_template(self)
    def handle_api_clear_telegram_cache(self): coupon_h.handle_clear_telegram_cache(self)
    def handle_api_regenerate_index(self): coupon_h.handle_regenerate_index(self)

    # Forex domain handlers
    def handle_api_forex_signals(self): forex_h.handle_forex_signals(self)
    def handle_api_forex_config_get(self): forex_h.handle_forex_config(self)
    def handle_api_forex_config_post(self): forex_h.handle_forex_config_post(self)
    def handle_api_forex_stats(self): forex_h.handle_forex_stats(self)
    def handle_api_forex_tp_config_get(self): forex_h.handle_forex_tp_config_get(self)
    def handle_api_forex_tp_config_post(self): forex_h.handle_forex_tp_config_post(self)
    def handle_api_xauusd_sparkline(self): forex_h.handle_xauusd_sparkline(self)
    def handle_api_signal_bot_status(self): forex_h.handle_signal_bot_status(self)
    def handle_api_signal_bot_signals(self): forex_h.handle_signal_bot_signals(self)
    def handle_api_signal_bot_set_active(self): forex_h.handle_signal_bot_set_active(self)
    def handle_api_signal_bot_cancel_queue(self): forex_h.handle_signal_bot_cancel_queue(self)

    # Telegram handlers
    def handle_api_telegram_channel_stats(self):
        tid = getattr(self, 'tenant_id', 'entrylab')
        sub_h.handle_telegram_channel_stats(self, tid)
    def handle_api_telegram_check_access(self): sub_h.handle_telegram_check_access(self)
    def handle_api_telegram_subscriptions(self): sub_h.handle_telegram_subscriptions(self)
    def handle_api_telegram_revenue_metrics(self): sub_h.handle_telegram_revenue_metrics(self)
    def handle_api_telegram_conversion_analytics(self): sub_h.handle_telegram_conversion_analytics(self)
    def handle_api_telegram_billing(self): sub_h.handle_telegram_billing(self)
    def handle_api_telegram_grant_access(self): sub_h.handle_telegram_grant_access(self)
    def handle_api_telegram_clear_all(self): sub_h.handle_telegram_clear_all(self)
    def handle_api_telegram_cleanup_test_data(self): sub_h.handle_telegram_cleanup_test_data(self)
    def handle_api_telegram_cancel_subscription(self): sub_h.handle_telegram_cancel_subscription(self)
    def handle_api_telegram_delete_subscription(self): sub_h.handle_telegram_delete_subscription(self)
    def handle_api_telegram_revoke_access(self): sub_h.handle_telegram_revoke_access(self)
    def handle_api_telegram_webhook(self): handle_coupon_telegram_webhook(self, TELEGRAM_BOT_AVAILABLE, telegram_bot)
    def handle_api_forex_telegram_webhook(self): handle_forex_telegram_webhook(self, TELEGRAM_BOT_AVAILABLE, telegram_bot)
    def handle_api_bot_webhook(self):
        path = self.path.split('?')[0]
        secret = path.replace('/api/bot-webhook/', '')
        handle_bot_webhook(self, secret)

    # Stripe handlers
    def handle_api_stripe_webhook(self): handle_stripe_webhook(self, STRIPE_AVAILABLE, TELEGRAM_BOT_AVAILABLE, db)
    def handle_api_stripe_sync(self): self._stripe_sync()
    def handle_api_stripe_status(self): stripe_h.handle_stripe_status(self)
    def handle_api_stripe_products(self): stripe_h.handle_stripe_products(self)
    def handle_api_stripe_sync_products(self): stripe_h.handle_stripe_sync_products(self)
    def handle_api_stripe_set_vip_price(self): stripe_h.handle_stripe_set_vip_price(self)

    def _stripe_sync(self):
        if not self.check_auth(): return self._json(401, {'error': 'Unauthorized'})
        if not STRIPE_AVAILABLE: return self._json(503, {'error': 'Stripe not available'})
        try:
            from stripe_client import fetch_active_subscriptions
            tid = getattr(self, 'tenant_id', 'entrylab')
            set_request_context(tenant_id=tid)
            subs = fetch_active_subscriptions()
            synced, errs = 0, []
            for s in subs:
                if s.get('email'):
                    r, e = db.create_or_update_telegram_subscription(email=s['email'], stripe_customer_id=s.get('customer_id'), stripe_subscription_id=s.get('subscription_id'), plan_type=s.get('plan_name') or 'premium', amount_paid=s.get('amount_paid', 0), name=s.get('name'), tenant_id=tid)
                    if r: synced += 1
                    else: errs.append(f"{s['email']}: {e}")
            self._json(200, {'success': True, 'synced': synced, 'total': len(subs), 'errors': errs})
        except Exception as e:
            logger.exception("Stripe sync error")
            self._json(500, {'error': str(e)})

    # Tenant handlers
    def handle_api_tenant_setup_status(self):
        tid = getattr(self, 'tenant_id', 'entrylab')
        set_request_context(tenant_id=tid)
        tenant_h.handle_tenant_setup_status(self, tid)

    def handle_api_tenant_integrations(self):
        tid = getattr(self, 'tenant_id', 'entrylab')
        set_request_context(tenant_id=tid)
        tenant_h.handle_tenant_integrations(self, tid)

    def handle_api_tenant_map_user(self): tenant_h.handle_tenant_map_user(self)

    # Onboarding handlers
    def handle_api_onboarding_state(self): onboard_h.handle_onboarding_state(self)
    def handle_api_onboarding_telegram(self): onboard_h.handle_onboarding_telegram(self)
    def handle_api_onboarding_stripe(self): onboard_h.handle_onboarding_stripe(self)
    def handle_api_onboarding_business(self): onboard_h.handle_onboarding_business(self)
    def handle_api_onboarding_complete(self): onboard_h.handle_onboarding_complete(self)

    # Journey handlers
    def handle_api_journeys_list(self):
        from domains.journeys import handlers as jh
        jh.handle_journeys_list(self)

    def handle_api_journey_get(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_get(self, urlparse(self.path).path.split('/')[3])

    def handle_api_journey_steps_get(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_steps_get(self, urlparse(self.path).path.split('/')[3])

    def handle_api_journeys_debug_sessions(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_sessions_debug(self)

    def handle_api_journey_create(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_create(self)

    def handle_api_journey_update(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_update(self, urlparse(self.path).path.split('/')[3])

    def handle_api_journey_steps_set(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_steps_set(self, urlparse(self.path).path.split('/')[3])

    def handle_api_journey_triggers(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_triggers(self, urlparse(self.path).path.split('/')[3])

    def handle_api_journey_delete(self):
        from domains.journeys import handlers as jh
        jh.handle_journey_delete(self, urlparse(self.path).path.split('/')[3])

    # Connection handlers
    def handle_api_connections_list(self):
        from domains.connections import handlers as conn_h
        conn_h.handle_connections_list(self)

    def handle_api_connection_validate(self):
        from domains.connections import handlers as conn_h
        conn_h.handle_connection_validate(self)

    def handle_api_connection_validate_saved(self):
        from domains.connections import handlers as conn_h
        conn_h.handle_connection_validate_saved(self)

    def handle_api_connection_test(self):
        from domains.connections import handlers as conn_h
        conn_h.handle_connection_test(self)

    def handle_api_connection_save(self):
        from domains.connections import handlers as conn_h
        conn_h.handle_connection_save(self)

    def handle_api_connection_delete(self):
        from domains.connections import handlers as conn_h
        bot_role = urlparse(self.path).path.split('/')[3]
        conn_h.handle_connection_delete(self, bot_role)

    # Cross Promo handlers
    def handle_api_crosspromo_settings_get(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_get_settings(self)

    def handle_api_crosspromo_settings_post(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_save_settings(self)

    def handle_api_crosspromo_jobs(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_list_jobs(self)

    def handle_api_crosspromo_run_daily(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_run_daily_sequence(self)

    def handle_api_crosspromo_publish_win(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_publish_win(self)

    def handle_api_crosspromo_send_test(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_send_test(self)

    def handle_api_crosspromo_preview(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_get_preview(self)

    def handle_api_crosspromo_test_cta(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_test_cta(self)

    def handle_api_crosspromo_test_forward_promo(self):
        from domains.crosspromo import handlers as cp_h
        cp_h.handle_test_forward_promo(self)

    # Legacy auth
    def handle_api_login(self):
        cl = int(self.headers.get('Content-Length', 0))
        try:
            d = json.loads(self.rfile.read(cl).decode())
            pw = Config.get_admin_password() or ''
            if d.get('password') == pw and pw:
                tok = create_admin_session()
                sec = '; Secure' if PORT == 8080 or Config.get_app_url().startswith('https') else ''
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Set-Cookie', f'admin_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{sec}')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self._json(401, {'success': False, 'error': 'Invalid password'})
        except Exception as e:
            self._json(500, {'success': False, 'error': str(e)})

    def handle_api_logout(self):
        sec = '; Secure' if PORT == 8080 or Config.get_app_url().startswith('https') else ''
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Set-Cookie', f'admin_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{sec}')
        self.send_header('Set-Cookie', f'clerk_user_email=; Path=/; SameSite=Lax; Max-Age=0{sec}')
        self.end_headers()
        self.wfile.write(json.dumps({'success': True}).encode())

    def handle_api_set_auth_cookie(self):
        from auth.clerk_auth import get_auth_user_from_request, is_admin_email
        from urllib.parse import quote
        from core.logging import get_logger
        log = get_logger('set_auth_cookie')
        u = get_auth_user_from_request(self)
        
        if not u:
            log.warning("set-auth-cookie: JWT verification failed - no user")
            self._json(401, {'error': 'unauthorized'})
            return
        
        email = u.get('email') or self.headers.get('X-Clerk-User-Email')
        log.info(f"set-auth-cookie: user={u.get('clerk_user_id')}, email={email}, is_admin={is_admin_email(email)}")
        
        if not is_admin_email(email):
            log.warning(f"set-auth-cookie: not admin email - {email}")
            self._json(403, {'error': 'forbidden'})
            return
        
        tok = create_admin_session()
        sec = '; Secure' if PORT == 8080 or Config.get_app_url().startswith('https') else ''
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Set-Cookie', f'admin_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{sec}')
        if email:
            encoded_email = quote(email, safe='')
            self.send_header('Set-Cookie', f'clerk_user_email={encoded_email}; Path=/; SameSite=Lax; Max-Age=86400{sec}')
        self.end_headers()
        self.wfile.write(json.dumps({'success': True, 'is_admin': True}).encode())
        log.info("set-auth-cookie: SUCCESS - cookies set")

    # Main HTTP methods
    def do_GET(self):
        set_request_context(request_id=None)
        hc = parse_host_context(self.headers.get('Host', '').lower())
        self.host_context = hc
        p = urlparse(self.path).path
        if p == '/':
            loc = '/admin' if hc.host_type == HostType.ADMIN else '/app' if hc.host_type == HostType.DASH else '/login'
            self.send_response(302)
            self.send_header('Location', loc)
            self.end_headers()
            return clear_request_context()
        if p == '/admin/':
            self.send_response(301)
            self.send_header('Location', '/admin')
            self.end_headers()
            return clear_request_context()
        if dispatch_request(self, 'GET', self.path, GET_ROUTES + PAGE_ROUTES + ADMIN_ROUTES, hc, DATABASE_AVAILABLE):
            return clear_request_context()
        super().do_GET()
        clear_request_context()

    def do_POST(self):
        set_request_context(request_id=None)
        hc = parse_host_context(self.headers.get('Host', '').lower())
        self.host_context = hc
        if dispatch_request(self, 'POST', self.path, POST_ROUTES + AUTH_ROUTES, hc, DATABASE_AVAILABLE):
            return clear_request_context()
        self.send_error(404, "Not Found")
        clear_request_context()

    def do_PUT(self):
        set_request_context(request_id=None)
        hc = parse_host_context(self.headers.get('Host', '').lower())
        self.host_context = hc
        if dispatch_request(self, 'PUT', self.path, PUT_ROUTES, hc, DATABASE_AVAILABLE):
            return clear_request_context()
        self.send_error(404, "Not Found")
        clear_request_context()

    def do_DELETE(self):
        set_request_context(request_id=None)
        hc = parse_host_context(self.headers.get('Host', '').lower())
        self.host_context = hc
        if dispatch_request(self, 'DELETE', self.path, DELETE_ROUTES, hc, DATABASE_AVAILABLE):
            return clear_request_context()
        self.send_error(404, "Not Found")
        clear_request_context()

if __name__ == "__main__":
    from core.app_context import create_app_context
    from core.bootstrap import start_app
    ctx = create_app_context()
    start_app(ctx)
    import sys
    sys.modules['server'] = sys.modules[__name__]
    import db as db_m, telegram_bot as tb_m, coupon_validator as cv_m
    db, telegram_bot, coupon_validator = db_m, tb_m, cv_m
    DATABASE_AVAILABLE = ctx.database_available
    TELEGRAM_BOT_AVAILABLE = ctx.telegram_bot_available
    COUPON_VALIDATOR_AVAILABLE = ctx.coupon_validator_available
    FOREX_SCHEDULER_AVAILABLE = ctx.forex_scheduler_available
    STRIPE_AVAILABLE = ctx.stripe_available
    OBJECT_STORAGE_AVAILABLE = ctx.object_storage_available
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Server running at http://0.0.0.0:{PORT}/")
        httpd.serve_forever()
