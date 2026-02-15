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
    # Config
    Route('GET', '/api/config', 'handle_api_config'),
    
    # Auth
    Route('GET', '/api/check-auth', 'handle_api_check_auth'),
    Route('GET', '/api/auth/debug', 'handle_api_auth_debug',
          auth_required=True),
    
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
    
    # Journey link click redirect (public, no auth)
    Route('GET', '/api/j/c/', 'handle_api_journey_link_click',
          is_prefix=True),

    # Journeys
    Route('GET', '/api/journeys/debug/sessions', 'handle_api_journeys_debug_sessions',
          auth_required=True, db_required=True),
    Route('GET', '/api/journeys/', 'handle_api_journey_analytics',
          auth_required=True, db_required=True, is_prefix=True, contains='/analytics'),
    Route('GET', '/api/journeys/', 'handle_api_journey_steps_get',
          auth_required=True, db_required=True, is_prefix=True, contains='/steps'),
    Route('GET', '/api/journeys/', 'handle_api_journey_get',
          auth_required=True, db_required=True, is_prefix=True),
    Route('GET', '/api/journeys', 'handle_api_journeys_list',
          auth_required=True, db_required=True),
    
    # Connections
    Route('GET', '/api/connections', 'handle_api_connections_list',
          auth_required=True, db_required=True),
    
    # Telethon (User Client)
    Route('GET', '/api/telethon/status', 'handle_api_telethon_status',
          auth_required=True),

    # Cross Promo
    Route('GET', '/api/crosspromo/settings', 'handle_api_crosspromo_settings_get',
          auth_required=True, db_required=True),
    Route('GET', '/api/crosspromo/jobs', 'handle_api_crosspromo_jobs',
          auth_required=True, db_required=True),
    Route('GET', '/api/crosspromo/preview', 'handle_api_crosspromo_preview',
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
    Route('POST', '/api/bot-webhook/', 'handle_api_bot_webhook', is_prefix=True),
    
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
    
    # Journeys
    Route('POST', '/api/journeys/', 'handle_api_journey_triggers',
          auth_required=True, db_required=True, is_prefix=True, contains='/triggers'),
    Route('POST', '/api/journeys', 'handle_api_journey_create',
          auth_required=True, db_required=True),
    
    # Connections
    Route('POST', '/api/connections/validate', 'handle_api_connection_validate',
          auth_required=True, db_required=True),
    Route('POST', '/api/connections/validate-saved', 'handle_api_connection_validate_saved',
          auth_required=True, db_required=True),
    Route('POST', '/api/connections/test', 'handle_api_connection_test',
          auth_required=True, db_required=True),
    Route('POST', '/api/connections', 'handle_api_connection_save',
          auth_required=True, db_required=True),
    
    # Telethon (User Client)
    Route('POST', '/api/telethon/send-code', 'handle_api_telethon_send_code',
          auth_required=True),
    Route('POST', '/api/telethon/verify-code', 'handle_api_telethon_verify_code',
          auth_required=True),
    Route('POST', '/api/telethon/verify-2fa', 'handle_api_telethon_verify_2fa',
          auth_required=True),
    Route('POST', '/api/telethon/reconnect', 'handle_api_telethon_reconnect',
          auth_required=True),
    Route('POST', '/api/telethon/disconnect', 'handle_api_telethon_disconnect',
          auth_required=True),

    # Cross Promo
    Route('POST', '/api/crosspromo/settings', 'handle_api_crosspromo_settings_post',
          auth_required=True, db_required=True),
    Route('POST', '/api/crosspromo/run-daily-seq', 'handle_api_crosspromo_run_daily',
          auth_required=True, db_required=True),
    Route('POST', '/api/crosspromo/publish-win', 'handle_api_crosspromo_publish_win',
          auth_required=True, db_required=True),
    Route('POST', '/api/crosspromo/send-test', 'handle_api_crosspromo_send_test',
          auth_required=True, db_required=True),
    Route('POST', '/api/crosspromo/test-cta', 'handle_api_crosspromo_test_cta',
          auth_required=True, db_required=True),
    Route('POST', '/api/crosspromo/test-forward-promo', 'handle_api_crosspromo_test_forward_promo',
          auth_required=True, db_required=True),
]


# ============================================================================
# PUT Routes
# ============================================================================

PUT_ROUTES: List[Route] = [
    # Journeys
    Route('PUT', '/api/journeys/', 'handle_api_journey_steps_set',
          auth_required=True, db_required=True, is_prefix=True, contains='/steps'),
    Route('PUT', '/api/journeys/', 'handle_api_journey_update',
          auth_required=True, db_required=True, is_prefix=True),
]


# ============================================================================
# DELETE Routes
# ============================================================================

DELETE_ROUTES: List[Route] = [
    # Journeys
    Route('DELETE', '/api/journeys/', 'handle_api_journey_delete',
          auth_required=True, db_required=True, is_prefix=True),
    
    # Connections
    Route('DELETE', '/api/connections/', 'handle_api_connection_delete',
          auth_required=True, db_required=True, is_prefix=True),
]


# ============================================================================
# Page Routes (HTML serving)
# ============================================================================

PAGE_ROUTES: List[Route] = [
    Route('GET', '/login', 'handle_page_login'),
    Route('GET', '/admin', 'handle_page_admin'),
    Route('GET', '/app', 'handle_page_app'),
    Route('GET', '/setup', 'handle_page_setup'),
    Route('GET', '/coupon', 'handle_page_coupon'),
    Route('GET', '/campaign/', 'handle_page_campaign', is_prefix=True),
    Route('GET', '/auth/me', 'handle_auth_me', db_required=True),
]

# ============================================================================
# Auth Routes (not API prefixed)
# ============================================================================

AUTH_ROUTES: List[Route] = [
    Route('POST', '/auth/logout', 'handle_auth_logout'),
]

# ============================================================================
# Admin Routes
# ============================================================================

ADMIN_ROUTES: List[Route] = [
    Route('GET', '/api/admin/tenants', 'handle_api_admin_tenants', auth_required=True, db_required=True),
]


# Combined routes for easy lookup
ALL_ROUTES = GET_ROUTES + POST_ROUTES + PUT_ROUTES + DELETE_ROUTES + PAGE_ROUTES + AUTH_ROUTES + ADMIN_ROUTES


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
