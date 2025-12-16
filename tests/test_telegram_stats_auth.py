"""Tests for telegram stats API auth and response shapes."""
import pytest
import sys
import json
from io import BytesIO
from unittest.mock import MagicMock, patch


class TestTelegramChannelStatsResponses:
    """Test /api/telegram-channel-stats response shapes."""
    
    def test_returns_503_when_bot_token_missing(self):
        """503 with code='bot_unavailable' when FOREX_BOT_TOKEN is missing."""
        import os
        
        with patch.dict(os.environ, {'FOREX_BOT_TOKEN': '', 'FOREX_CHANNEL_ID': '@test'}):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler)
        
        handler.send_response.assert_called_with(503)
        response = json.loads(handler.wfile.getvalue())
        assert response['ok'] is False
        assert response['code'] == 'bot_unavailable'
    
    def test_returns_503_when_channel_not_configured(self):
        """503 with code='channel_not_configured' when FOREX_CHANNEL_ID is missing."""
        import os
        
        with patch.dict(os.environ, {'FOREX_BOT_TOKEN': 'test_token', 'FOREX_CHANNEL_ID': ''}):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler)
        
        handler.send_response.assert_called_with(503)
        response = json.loads(handler.wfile.getvalue())
        assert response['ok'] is False
        assert response['code'] == 'channel_not_configured'
    
    def test_returns_200_with_member_count_on_success(self):
        """200 with ok=true and member_count on successful API call."""
        import os
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'result': 1234}
        
        with patch.dict(os.environ, {'FOREX_BOT_TOKEN': 'test_token', 'FOREX_CHANNEL_ID': '@test_channel'}), \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler)
        
        handler.send_response.assert_called_with(200)
        response = json.loads(handler.wfile.getvalue())
        assert response['ok'] is True
        assert response['member_count'] == 1234
        assert response['channel_id'] == '@test_channel'
    
    def test_returns_502_on_telegram_api_error(self):
        """502 with code='telegram_api_error' when API call fails."""
        import os
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': False, 'description': 'Bad Request'}
        
        with patch.dict(os.environ, {'FOREX_BOT_TOKEN': 'test_token', 'FOREX_CHANNEL_ID': '@test_channel'}), \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler)
        
        handler.send_response.assert_called_with(502)
        response = json.loads(handler.wfile.getvalue())
        assert response['ok'] is False
        assert response['code'] == 'telegram_api_error'


class TestCheckAuthResponses:
    """Test /api/check-auth response shapes."""
    
    def test_returns_authenticated_true_with_valid_admin_session(self):
        """check-auth returns authenticated:true when admin_session cookie is valid."""
        import os
        os.environ.setdefault('ADMIN_PASSWORD', 'test_secret')
        
        from auth.clerk_auth import create_admin_session, verify_admin_session
        
        token = create_admin_session()
        assert verify_admin_session(token) is True
    
    def test_returns_authenticated_false_with_expired_session(self):
        """check-auth returns authenticated:false for expired session."""
        import time
        import hmac
        import hashlib
        from auth.clerk_auth import verify_admin_session
        from core.config import Config
        
        expired_ts = int(time.time()) - 100
        secret = Config.get_admin_password() or 'test'
        sig = hmac.new(secret.encode(), str(expired_ts).encode(), hashlib.sha256).hexdigest()
        expired_token = f"{expired_ts}.{sig}"
        
        assert verify_admin_session(expired_token) is False
    
    def test_x_clerk_user_email_alone_returns_none(self):
        """X-Clerk-User-Email header alone should NOT authenticate."""
        from auth.clerk_auth import get_auth_user_from_request
        
        handler = MagicMock()
        handler.headers = {'X-Clerk-User-Email': 'admin@example.com'}
        handler.client_address = ('127.0.0.1', 12345)
        handler.path = '/api/check-auth'
        
        result = get_auth_user_from_request(handler, record_failure=False)
        assert result is None
