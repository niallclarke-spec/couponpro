"""
Route definitions for the HTTP API.

Each Route maps (method, path) to a handler method name on MyHTTPRequestHandler.
Handler names are validated at startup to fail fast if any are missing.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Route:
    """
    A route definition mapping HTTP method + path to a handler.
    
    Attributes:
        method: HTTP method ('GET' or 'POST')
        path: URL path (exact match or prefix if is_prefix=True)
        handler: Method name on MyHTTPRequestHandler (validated at startup)
        auth_required: If True, check_auth() must pass before handler runs
        db_required: If True, DATABASE_AVAILABLE must be True
        is_prefix: If True, match path.startswith() instead of ==
        contains: Optional substring that must also be in the path (for compound matches)
    """
    method: str
    path: str
    handler: str
    auth_required: bool = False
    db_required: bool = False
    is_prefix: bool = False
    contains: Optional[str] = None


# ============================================================================
# GET Routes
# ============================================================================

GET_ROUTES: List[Route] = [
    # Auth
    Route('GET', '/api/check-auth', 'handle_api_check_auth'),
    
    # Campaigns (order matters: more specific patterns first)
    Route('GET', '/api/campaigns/', 'handle_api_campaign_submissions',
          auth_required=True, db_required=True, is_prefix=True, contains='/submissions'),
    Route('GET', '/api/campaigns/', 'handle_api_campaign_by_id',
          db_required=True, is_prefix=True),
    Route('GET', '/api/campaigns', 'handle_api_campaigns', db_required=True),
    
    # Bot stats
    Route('GET', '/api/bot-stats', 'handle_api_bot_stats',
          auth_required=True, db_required=True),
    Route('GET', '/api/day-of-week-stats', 'handle_api_day_of_week_stats',
          auth_required=True, db_required=True),
    Route('GET', '/api/retention-rates', 'handle_api_retention_rates',
          auth_required=True, db_required=True),
    
    # Forex
    Route('GET', '/api/forex-signals', 'handle_api_forex_signals',
          auth_required=True, db_required=True),
    Route('GET', '/api/forex-config', 'handle_api_forex_config_get',
          auth_required=True, db_required=True),
    Route('GET', '/api/forex-stats', 'handle_api_forex_stats',
          auth_required=True, db_required=True),
    Route('GET', '/api/forex-tp-config', 'handle_api_forex_tp_config_get',
          auth_required=True, db_required=True),
    Route('GET', '/api/forex/xauusd-sparkline', 'handle_api_xauusd_sparkline',
          auth_required=True),
    
    # Signal bot
    Route('GET', '/api/signal-bot/status', 'handle_api_signal_bot_status',
          auth_required=True, db_required=True),
    Route('GET', '/api/signal-bot/signals', 'handle_api_signal_bot_signals',
          auth_required=True, db_required=True),
    
    # Telegram
    Route('GET', '/api/telegram-channel-stats', 'handle_api_telegram_channel_stats',
          auth_required=True),
    Route('GET', '/api/telegram/check-access/', 'handle_api_telegram_check_access',
          is_prefix=True),
    Route('GET', '/api/telegram-subscriptions', 'handle_api_telegram_subscriptions',
          auth_required=True, db_required=True),
    Route('GET', '/api/telegram/revenue-metrics', 'handle_api_telegram_revenue_metrics',
          auth_required=True),
    Route('GET', '/api/telegram/conversion-analytics', 'handle_api_telegram_conversion_analytics',
          auth_required=True),
    Route('GET', '/api/telegram/billing/', 'handle_api_telegram_billing',
          auth_required=True, is_prefix=True),
    
    # Broadcast
    Route('GET', '/api/broadcast-status/', 'handle_api_broadcast_status',
          auth_required=True, db_required=True, is_prefix=True),
    Route('GET', '/api/broadcast-jobs', 'handle_api_broadcast_jobs',
          auth_required=True, db_required=True),
    
    # Users
    Route('GET', '/api/bot-users', 'handle_api_bot_users',
          auth_required=True, db_required=True),
    Route('GET', '/api/user-activity/', 'handle_api_user_activity',
          auth_required=True, db_required=True, is_prefix=True),
    
    # Invalid coupons
    Route('GET', '/api/invalid-coupons', 'handle_api_invalid_coupons',
          auth_required=True, db_required=True),
    
    # Tenant
    Route('GET', '/api/tenant/setup-status', 'handle_api_tenant_setup_status',
          auth_required=True, db_required=True),
    
    # Onboarding
    Route('GET', '/api/onboarding/state', 'handle_api_onboarding_state',
          auth_required=True, db_required=True),
    
    # Stripe Products
    Route('GET', '/api/stripe/status', 'handle_api_stripe_status',
          auth_required=True, db_required=True),
    Route('GET', '/api/stripe/products', 'handle_api_stripe_products',
          auth_required=True, db_required=True),
]


# ============================================================================
# POST Routes
# ============================================================================

POST_ROUTES: List[Route] = [
    # Coupon validation (no auth - public API)
    Route('POST', '/api/validate-coupon', 'handle_api_validate_coupon'),
    
    # Broadcast
    Route('POST', '/api/broadcast', 'handle_api_broadcast',
          auth_required=True, db_required=True),
    
    # Auth
    Route('POST', '/api/login', 'handle_api_login'),
    Route('POST', '/api/logout', 'handle_api_logout'),
    
    # Forex config
    Route('POST', '/api/forex-config', 'handle_api_forex_config_post',
          auth_required=True, db_required=True),
    Route('POST', '/api/forex-tp-config', 'handle_api_forex_tp_config_post',
          auth_required=True, db_required=True),
    
    # Signal bot
    Route('POST', '/api/signal-bot/set-active', 'handle_api_signal_bot_set_active',
          auth_required=True, db_required=True),
    Route('POST', '/api/signal-bot/cancel-queue', 'handle_api_signal_bot_cancel_queue',
          auth_required=True, db_required=True),
    
    # Template management
    Route('POST', '/api/upload-overlay', 'handle_api_upload_overlay',
          auth_required=True),
    Route('POST', '/api/upload-template', 'handle_api_upload_template',
          auth_required=True),
    Route('POST', '/api/delete-template', 'handle_api_delete_template',
          auth_required=True),
    Route('POST', '/api/toggle-telegram-template', 'handle_api_toggle_telegram_template',
          auth_required=True),
    Route('POST', '/api/clear-telegram-cache', 'handle_api_clear_telegram_cache',
          auth_required=True),
    Route('POST', '/api/regenerate-index', 'handle_api_regenerate_index'),
    
    # Telegram webhooks (no auth - webhook endpoints)
    Route('POST', '/api/telegram-webhook', 'handle_api_telegram_webhook'),
    Route('POST', '/api/forex-telegram-webhook', 'handle_api_forex_telegram_webhook'),
    
    # Telegram management
    Route('POST', '/api/telegram/grant-access', 'handle_api_telegram_grant_access'),
    Route('POST', '/api/telegram/clear-all', 'handle_api_telegram_clear_all'),
    Route('POST', '/api/telegram/cleanup-test-data', 'handle_api_telegram_cleanup_test_data',
          auth_required=True),
    Route('POST', '/api/telegram/cancel-subscription', 'handle_api_telegram_cancel_subscription',
          auth_required=True),
    Route('POST', '/api/telegram/delete-subscription', 'handle_api_telegram_delete_subscription',
          auth_required=True),
    Route('POST', '/api/telegram/revoke-access', 'handle_api_telegram_revoke_access'),
    
    # Stripe
    Route('POST', '/api/stripe/webhook', 'handle_api_stripe_webhook'),
    Route('POST', '/api/stripe/sync', 'handle_api_stripe_sync',
          auth_required=True),
    Route('POST', '/api/stripe/sync-products', 'handle_api_stripe_sync_products',
          auth_required=True, db_required=True),
    Route('POST', '/api/stripe/set-vip-price', 'handle_api_stripe_set_vip_price',
          auth_required=True, db_required=True),
    
    # Campaigns (POST)
    Route('POST', '/api/campaigns/', 'handle_api_campaign_submit',
          db_required=True, is_prefix=True, contains='/submit'),
    Route('POST', '/api/campaigns/', 'handle_api_campaign_update',
          auth_required=True, db_required=True, is_prefix=True, contains='/update'),
    Route('POST', '/api/campaigns/', 'handle_api_campaign_delete',
          auth_required=True, db_required=True, is_prefix=True, contains='/delete'),
    Route('POST', '/api/campaigns', 'handle_api_campaigns_create',
          auth_required=True, db_required=True),
    
    # Tenant
    Route('POST', '/api/tenant/integrations', 'handle_api_tenant_integrations',
          auth_required=True, db_required=True),
    Route('POST', '/api/tenants/map-user', 'handle_api_tenant_map_user',
          auth_required=True, db_required=True),
    
    # Auth cookie
    Route('POST', '/api/set-auth-cookie', 'handle_api_set_auth_cookie'),
    
    # Onboarding
    Route('POST', '/api/onboarding/telegram', 'handle_api_onboarding_telegram',
          auth_required=True, db_required=True),
    Route('POST', '/api/onboarding/stripe', 'handle_api_onboarding_stripe',
          auth_required=True, db_required=True),
    Route('POST', '/api/onboarding/business', 'handle_api_onboarding_business',
          auth_required=True, db_required=True),
    Route('POST', '/api/onboarding/complete', 'handle_api_onboarding_complete',
          auth_required=True, db_required=True),
]


# ============================================================================
# Page Routes (HTML serving)
# ============================================================================

PAGE_ROUTES: List[Route] = [
    # Note: /admin and /admin/ are NOT in PAGE_ROUTES because they handle
    # their own auth in server.py and don't need tenant mapping checks
    Route('GET', '/campaign/', 'handle_campaign_page', is_prefix=True),
]


# Combined routes for easy lookup
ALL_ROUTES = GET_ROUTES + POST_ROUTES + PAGE_ROUTES


def match_route(method: str, path: str, routes: List[Route]) -> Optional[Route]:
    """
    Find a matching route for the given method and path.
    
    Routes are checked in order, so more specific patterns should come first.
    
    Args:
        method: HTTP method ('GET' or 'POST')
        path: URL path to match
        routes: List of routes to search
    
    Returns:
        Matching Route or None
    """
    for route in routes:
        if route.method != method:
            continue
        
        if route.is_prefix:
            if not path.startswith(route.path):
                continue
            if route.contains and route.contains not in path:
                continue
            return route
        else:
            if path == route.path:
                return route
    
    return None


def validate_routes(handler_class) -> None:
    """
    Validate that all route handlers exist on the handler class.
    
    Call this at startup to fail fast if any handlers are missing.
    
    Args:
        handler_class: The request handler class (MyHTTPRequestHandler)
    
    Raises:
        AttributeError: If any handler method is missing
    """
    missing = []
    for route in ALL_ROUTES:
        if not hasattr(handler_class, route.handler):
            missing.append(f"{route.method} {route.path} -> {route.handler}")
    
    if missing:
        raise AttributeError(
            f"Missing handler methods on {handler_class.__name__}:\n" +
            "\n".join(f"  - {m}" for m in missing)
        )
