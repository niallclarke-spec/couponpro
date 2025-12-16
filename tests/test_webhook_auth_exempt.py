"""
Regression tests for webhook auth exemption.

These tests ensure that webhook endpoints remain auth-exempt,
preventing regressions like Telegram webhooks returning 403 due
to missing cookies/auth headers.

Webhooks are called by external services (Telegram, Stripe) that
will NEVER send browser cookies or JWT tokens.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.middleware import (
    is_webhook_exempt_route,
    WEBHOOK_EXEMPT_ROUTES,
    apply_route_checks
)
from api.routes import Route


class TestWebhookAuthExemption:
    """Test that webhook routes are properly exempted from auth."""
    
    def test_telegram_webhook_is_exempt(self):
        """Telegram webhook must be auth-exempt."""
        assert is_webhook_exempt_route('/api/telegram-webhook'), \
            "/api/telegram-webhook must be auth-exempt"
    
    def test_forex_telegram_webhook_is_exempt(self):
        """Forex telegram webhook must be auth-exempt."""
        assert is_webhook_exempt_route('/api/forex-telegram-webhook'), \
            "/api/forex-telegram-webhook must be auth-exempt"
    
    def test_stripe_webhook_is_exempt(self):
        """Stripe webhook must be auth-exempt."""
        assert is_webhook_exempt_route('/api/stripe/webhook'), \
            "/api/stripe/webhook must be auth-exempt"
    
    def test_bot_webhook_with_secret_is_exempt(self):
        """Bot webhook with secret path must be auth-exempt."""
        assert is_webhook_exempt_route('/api/bot-webhook/some-secret'), \
            "/api/bot-webhook/{secret} must be auth-exempt"
    
    def test_telegram_webhook_with_query_string_is_exempt(self):
        """Webhook paths with query strings must also be exempt."""
        assert is_webhook_exempt_route('/api/telegram-webhook?foo=bar'), \
            "Webhook paths with query strings must be auth-exempt"
    
    def test_non_webhook_routes_are_not_exempt(self):
        """Non-webhook routes should NOT be marked as webhook-exempt."""
        non_webhook_routes = [
            '/api/bot-stats',
            '/api/telegram-channel-stats',
            '/api/forex-signals',
            '/api/campaigns',
            '/admin',
        ]
        for route in non_webhook_routes:
            assert not is_webhook_exempt_route(route), \
                f"{route} should NOT be webhook-exempt"
    
    def test_webhook_exempt_routes_list_has_required_paths(self):
        """Verify all required webhook paths are in the exempt list."""
        required_webhooks = [
            '/api/telegram-webhook',
            '/api/forex-telegram-webhook',
            '/api/stripe/webhook',
            '/api/bot-webhook/',
        ]
        for webhook in required_webhooks:
            assert webhook in WEBHOOK_EXEMPT_ROUTES, \
                f"{webhook} must be in WEBHOOK_EXEMPT_ROUTES"


class TestAuthenticatedRoutesRequireAuth:
    """Test that authenticated routes still require auth."""
    
    def test_channel_stats_route_requires_auth(self):
        """Authenticated routes should NOT be webhook-exempt."""
        assert not is_webhook_exempt_route('/api/telegram-channel-stats'), \
            "Channel stats route should require auth"
    
    def test_bot_stats_route_requires_auth(self):
        """Bot stats route should require auth."""
        assert not is_webhook_exempt_route('/api/bot-stats'), \
            "Bot stats route should require auth"
    
    def test_forex_signals_route_requires_auth(self):
        """Forex signals route should require auth."""
        assert not is_webhook_exempt_route('/api/forex-signals'), \
            "Forex signals route should require auth"


class TestRouteAuthConfiguration:
    """Test that Route auth_required flags are correctly set."""
    
    def test_telegram_webhook_route_has_no_auth_required(self):
        """Telegram webhook route must have auth_required=False."""
        from api.routes import POST_ROUTES, match_route
        
        route = match_route('POST', '/api/telegram-webhook', POST_ROUTES)
        assert route is not None, "Telegram webhook route must exist"
        assert route.auth_required == False, \
            "Telegram webhook route must have auth_required=False"
    
    def test_forex_telegram_webhook_route_has_no_auth_required(self):
        """Forex telegram webhook route must have auth_required=False."""
        from api.routes import POST_ROUTES, match_route
        
        route = match_route('POST', '/api/forex-telegram-webhook', POST_ROUTES)
        assert route is not None, "Forex telegram webhook route must exist"
        assert route.auth_required == False, \
            "Forex telegram webhook route must have auth_required=False"
    
    def test_stripe_webhook_route_has_no_auth_required(self):
        """Stripe webhook route must have auth_required=False."""
        from api.routes import POST_ROUTES, match_route
        
        route = match_route('POST', '/api/stripe/webhook', POST_ROUTES)
        assert route is not None, "Stripe webhook route must exist"
        assert route.auth_required == False, \
            "Stripe webhook route must have auth_required=False"
    
    def test_authenticated_route_has_auth_required(self):
        """Authenticated routes must have auth_required=True."""
        from api.routes import GET_ROUTES, match_route
        
        route = match_route('GET', '/api/telegram-channel-stats', GET_ROUTES)
        assert route is not None, "Channel stats route must exist"
        assert route.auth_required == True, \
            "Channel stats route must have auth_required=True"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
