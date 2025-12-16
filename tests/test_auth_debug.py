"""
Tests for auth debug ring buffer and diagnostics.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestAuthDebugRingBuffer:
    """Tests for auth failure recording and retrieval."""
    
    def test_records_auth_failure(self):
        """Should record auth failures to ring buffer."""
        from auth.auth_debug import record_auth_failure, get_recent_failures, clear_failures, AuthFailureReason
        
        clear_failures()
        
        record_auth_failure(
            reason=AuthFailureReason.MISSING_AUTH_HEADER,
            path='/api/check-auth',
            host='localhost',
            token_source='none'
        )
        
        failures = get_recent_failures()
        assert len(failures) == 1
        assert failures[0]['reason'] == AuthFailureReason.MISSING_AUTH_HEADER
        assert failures[0]['path'] == '/api/check-auth'
        
        clear_failures()
    
    def test_buffer_limit(self):
        """Should limit buffer to 50 entries."""
        from auth.auth_debug import record_auth_failure, get_recent_failures, clear_failures, get_failure_count, AuthFailureReason
        
        clear_failures()
        
        for i in range(60):
            record_auth_failure(
                reason=AuthFailureReason.TOKEN_EXPIRED,
                path=f'/api/test/{i}'
            )
        
        assert get_failure_count() == 50
        failures = get_recent_failures()
        assert len(failures) == 50
        assert failures[0]['path'] == '/api/test/59'
        
        clear_failures()
    
    def test_newest_first(self):
        """Should return failures newest first."""
        from auth.auth_debug import record_auth_failure, get_recent_failures, clear_failures, AuthFailureReason
        
        clear_failures()
        
        record_auth_failure(reason=AuthFailureReason.TOKEN_EXPIRED, path='/api/first')
        record_auth_failure(reason=AuthFailureReason.INVALID_SIGNATURE, path='/api/second')
        record_auth_failure(reason=AuthFailureReason.MISSING_CLAIMS, path='/api/third')
        
        failures = get_recent_failures()
        assert failures[0]['path'] == '/api/third'
        assert failures[1]['path'] == '/api/second'
        assert failures[2]['path'] == '/api/first'
        
        clear_failures()


class TestAuthFailureRecording:
    """Tests for auth failure recording from verify flow."""
    
    def test_records_missing_header_failure(self):
        """Should record failure when no auth header present."""
        from auth.clerk_auth import get_auth_user_from_request
        from auth.auth_debug import get_recent_failures, clear_failures, AuthFailureReason
        
        clear_failures()
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': '', 'Cookie': ''}
        mock_request.path = '/api/test-endpoint'
        
        result = get_auth_user_from_request(mock_request, record_failure=True)
        
        assert result is None
        failures = get_recent_failures()
        assert len(failures) >= 1
        latest = failures[0]
        assert latest['reason'] == AuthFailureReason.MISSING_AUTH_HEADER
        assert latest['path'] == '/api/test-endpoint'
        
        clear_failures()
    
    def test_records_token_expired_failure(self):
        """Should record failure when token is expired."""
        import jwt
        import os
        from auth.clerk_auth import get_auth_user_from_request
        from auth.auth_debug import get_recent_failures, clear_failures, AuthFailureReason
        
        clear_failures()
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer expired.jwt.token', 'Cookie': ''}
        mock_request.path = '/api/expired-test'
        
        with patch.dict(os.environ, {'CLERK_JWKS_URL': 'https://example.com/.well-known/jwks.json'}):
            with patch('auth.clerk_auth._get_jwks_client') as mock_client:
                mock_key = MagicMock()
                mock_key.key = 'fake_key'
                mock_client.return_value.get_signing_key_from_jwt.return_value = mock_key
                
                with patch('jwt.decode', side_effect=jwt.ExpiredSignatureError("Token expired")):
                    result = get_auth_user_from_request(mock_request, record_failure=True)
        
        assert result is None
        failures = get_recent_failures()
        assert len(failures) >= 1
        latest = failures[0]
        assert latest['reason'] == AuthFailureReason.TOKEN_EXPIRED
        assert latest['path'] == '/api/expired-test'
        assert latest['token_source'] == 'bearer'
        
        clear_failures()


class TestAuthDebugEndpoint:
    """Tests for /api/auth/debug endpoint."""
    
    def test_auth_debug_route_exists(self):
        """Verify /api/auth/debug route is defined."""
        from api.routes import GET_ROUTES
        
        paths = [r.path for r in GET_ROUTES]
        assert '/api/auth/debug' in paths
    
    def test_auth_debug_requires_auth(self):
        """Verify auth debug route requires authentication."""
        from api.routes import GET_ROUTES
        
        route = next((r for r in GET_ROUTES if r.path == '/api/auth/debug'), None)
        assert route is not None
        assert route.auth_required is True
    
    def test_handler_exists(self):
        """Verify handler method exists on server."""
        import server
        
        assert hasattr(server.MyHTTPRequestHandler, 'handle_api_auth_debug')


class TestTelegramChannelStatsErrorCodes:
    """Tests for improved telegram channel stats error handling."""
    
    def test_returns_503_when_bot_unavailable(self):
        """Should return 503 when telegram bot is not available."""
        from domains.subscriptions.handlers import handle_telegram_channel_stats
        from io import BytesIO
        import json
        
        mock_handler = MagicMock()
        mock_handler.wfile = BytesIO()
        
        with patch('server.TELEGRAM_BOT_AVAILABLE', False):
            handle_telegram_channel_stats(mock_handler)
        
        mock_handler.send_response.assert_called_with(503)
        mock_handler.wfile.seek(0)
        response = json.loads(mock_handler.wfile.read().decode())
        assert response['code'] == 'bot_unavailable'
    
    def test_returns_503_when_channel_not_configured(self):
        """Should return 503 when channel ID is not configured."""
        from domains.subscriptions.handlers import handle_telegram_channel_stats
        from io import BytesIO
        import json
        
        mock_handler = MagicMock()
        mock_handler.wfile = BytesIO()
        
        with patch('server.TELEGRAM_BOT_AVAILABLE', True):
            with patch('core.config.Config.get_forex_channel_id', return_value=None):
                handle_telegram_channel_stats(mock_handler)
        
        mock_handler.send_response.assert_called_with(503)
        mock_handler.wfile.seek(0)
        response = json.loads(mock_handler.wfile.read().decode())
        assert response['code'] == 'channel_not_configured'
