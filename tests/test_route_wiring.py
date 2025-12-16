"""
Regression tests for route wiring and handler existence.
Ensures routes, server methods, and domain handlers are all connected.
"""
import pytest
import importlib


class TestRouteWiring:
    """Tests to verify routes are properly wired to handlers."""
    
    def test_telegram_channel_stats_route_exists(self):
        """Verify /api/telegram-channel-stats route is defined."""
        from api.routes import GET_ROUTES
        
        paths = [r.path for r in GET_ROUTES]
        assert '/api/telegram-channel-stats' in paths
    
    def test_telegram_channel_stats_requires_auth(self):
        """Verify route requires authentication."""
        from api.routes import GET_ROUTES
        
        route = next((r for r in GET_ROUTES if r.path == '/api/telegram-channel-stats'), None)
        assert route is not None
        assert route.auth_required is True
    
    def test_server_has_wrapper_method(self):
        """Verify server.py has the wrapper method."""
        import server
        
        handler_class = server.MyHTTPRequestHandler
        assert hasattr(handler_class, 'handle_api_telegram_channel_stats')
    
    def test_domain_handler_exists(self):
        """Verify domain handler function exists and is callable."""
        from domains.subscriptions import handlers
        
        assert hasattr(handlers, 'handle_telegram_channel_stats')
        assert callable(handlers.handle_telegram_channel_stats)


class TestJourneysRouteWiring:
    """Tests for journeys API route wiring."""
    
    def test_journeys_list_route_exists(self):
        """Verify /api/journeys route exists."""
        from api.routes import GET_ROUTES
        
        paths = [r.path for r in GET_ROUTES]
        assert '/api/journeys' in paths
    
    def test_journeys_route_requires_auth(self):
        """Verify journeys route requires auth."""
        from api.routes import GET_ROUTES
        
        route = next((r for r in GET_ROUTES if r.path == '/api/journeys'), None)
        assert route is not None
        assert route.auth_required is True


class TestAuthParsing:
    """Tests for auth token parsing."""
    
    def test_recognizes_bearer_token(self):
        """Verify Bearer token is extracted from Authorization header."""
        from auth.clerk_auth import get_auth_user_from_request
        from unittest.mock import MagicMock, patch
        
        mock_request = MagicMock()
        mock_request.headers = {
            'Authorization': 'Bearer test.jwt.token',
            'Cookie': ''
        }
        
        mock_user = {
            'clerk_user_id': 'user_123',
            'email': 'test@example.com',
            'name': 'Test',
            'avatar_url': None
        }
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value=mock_user) as mock_verify:
            result = get_auth_user_from_request(mock_request)
            mock_verify.assert_called_once_with('test.jwt.token')
            assert result == mock_user
    
    def test_recognizes_session_cookie(self):
        """Verify __session cookie is extracted."""
        from auth.clerk_auth import get_auth_user_from_request
        from unittest.mock import MagicMock, patch
        
        mock_request = MagicMock()
        mock_request.headers = {
            'Authorization': '',
            'Cookie': '__session=cookie.jwt.token'
        }
        
        mock_user = {
            'clerk_user_id': 'user_456',
            'email': 'cookie@example.com',
            'name': 'Cookie User',
            'avatar_url': None
        }
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value=mock_user) as mock_verify:
            result = get_auth_user_from_request(mock_request)
            mock_verify.assert_called_once_with('cookie.jwt.token')
            assert result == mock_user
    
    def test_bearer_takes_precedence_over_cookie(self):
        """Verify Bearer token is used when both are present."""
        from auth.clerk_auth import get_auth_user_from_request
        from unittest.mock import MagicMock, patch
        
        mock_request = MagicMock()
        mock_request.headers = {
            'Authorization': 'Bearer bearer.token',
            'Cookie': '__session=cookie.token'
        }
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value={'clerk_user_id': 'test'}) as mock_verify:
            get_auth_user_from_request(mock_request)
            mock_verify.assert_called_once_with('bearer.token')
    
    def test_returns_none_when_no_token(self):
        """Verify None is returned when no token present."""
        from auth.clerk_auth import get_auth_user_from_request
        from unittest.mock import MagicMock
        
        mock_request = MagicMock()
        mock_request.headers = {
            'Authorization': '',
            'Cookie': ''
        }
        
        result = get_auth_user_from_request(mock_request)
        assert result is None
    
    def test_x_clerk_user_email_alone_not_valid(self):
        """Verify X-Clerk-User-Email header alone does NOT authenticate."""
        from auth.clerk_auth import get_auth_user_from_request
        from unittest.mock import MagicMock
        
        mock_request = MagicMock()
        mock_request.headers = {
            'Authorization': '',
            'Cookie': '',
            'X-Clerk-User-Email': 'attacker@example.com'
        }
        
        result = get_auth_user_from_request(mock_request)
        assert result is None
