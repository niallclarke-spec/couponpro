"""Tests for telegram stats API auth and response shapes."""
import pytest
import sys
import json
from io import BytesIO
from unittest.mock import MagicMock, patch


class TestTelegramChannelStatsResponses:
    """Test /api/telegram-channel-stats response shapes with BotCredentialResolver."""
    
    def test_returns_503_when_bot_not_configured(self):
        """503 with error_code='bot_not_configured' when signal_bot not in DB."""
        from core.bot_credentials import BotNotConfiguredError
        
        with patch('core.bot_credentials.get_bot_credentials') as mock_get_creds:
            mock_get_creds.side_effect = BotNotConfiguredError('entrylab', 'signal_bot')
            
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(503)
        response = json.loads(handler.wfile.getvalue())
        assert response['success'] is False
        assert response['error_code'] == 'bot_not_configured'
        assert 'Signal Bot not configured' in response['message']
        assert response['tenant_id'] == 'entrylab'
        assert response['bot_role'] == 'signal_bot'
    
    def test_returns_503_when_channel_id_missing(self):
        """503 with error_code='channel_id_missing' when channel_id not set."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': None,
            'webhook_url': None
        }
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(503)
        response = json.loads(handler.wfile.getvalue())
        assert response['success'] is False
        assert response['error_code'] == 'channel_id_missing'
        assert 'channel_id missing' in response['message']
        assert response['bot_username'] == 'test_bot'
    
    def test_returns_200_with_member_count_on_success(self):
        """200 with success=true and member_count when Telegram API succeeds."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'result': 1234}
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials), \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(200)
        response = json.loads(handler.wfile.getvalue())
        assert response['success'] is True
        assert response['member_count'] == 1234
        assert response['channel_id'] == '-100123456789'
        assert response['bot_username'] == 'test_bot'
        assert response['tenant_id'] == 'entrylab'
    
    def test_returns_502_when_telegram_api_fails(self):
        """502 with error_code='telegram_api_error' when Telegram returns error."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'ok': False, 
            'description': 'Bad Request: chat not found',
            'error_code': 400
        }
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials), \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(502)
        response = json.loads(handler.wfile.getvalue())
        assert response['success'] is False
        assert response['error_code'] == 'telegram_api_error'
        assert 'Channel not found' in response['message']
        assert response['telegram_error'] == 'Bad Request: chat not found'
    
    def test_returns_actionable_message_for_not_enough_rights(self):
        """Actionable message when bot doesn't have permission."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'ok': False, 
            'description': 'Bad Request: not enough rights to get chat members count',
            'error_code': 400
        }
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials), \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(502)
        response = json.loads(handler.wfile.getvalue())
        assert 'Add the bot to the channel' in response['message']
    
    def test_returns_502_on_timeout(self):
        """502 with error_code='telegram_timeout' when API times out."""
        import requests
        
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials), \
             patch('requests.get', side_effect=requests.Timeout('Connection timed out')):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='entrylab')
        
        handler.send_response.assert_called_with(502)
        response = json.loads(handler.wfile.getvalue())
        assert response['success'] is False
        assert response['error_code'] == 'telegram_timeout'
        assert 'timed out' in response['message'].lower()
    
    def test_uses_signal_bot_role(self):
        """Handler queries signal_bot role from BotCredentialResolver."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'result': 100}
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials) as mock_get_creds, \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id='test_tenant')
        
        mock_get_creds.assert_called_once_with('test_tenant', 'signal_bot')
    
    def test_defaults_to_entrylab_tenant(self):
        """Uses 'entrylab' tenant when tenant_id is None."""
        mock_credentials = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': '-100123456789',
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True, 'result': 100}
        
        with patch('core.bot_credentials.get_bot_credentials', return_value=mock_credentials) as mock_get_creds, \
             patch('requests.get', return_value=mock_response):
            from domains.subscriptions import handlers
            
            handler = MagicMock()
            handler.wfile = BytesIO()
            handlers.handle_telegram_channel_stats(handler, tenant_id=None)
        
        mock_get_creds.assert_called_once_with('entrylab', 'signal_bot')
        response = json.loads(handler.wfile.getvalue())
        assert response['tenant_id'] == 'entrylab'


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


class TestActionableErrorMessages:
    """Test actionable error message mapping."""
    
    def test_chat_not_found_message(self):
        """Maps 'chat not found' to helpful message about channel ID format."""
        from domains.subscriptions.handlers import _get_actionable_telegram_error
        
        msg = _get_actionable_telegram_error('Bad Request: chat not found')
        assert 'Channel not found' in msg
        assert '-100' in msg
    
    def test_not_enough_rights_message(self):
        """Maps 'not enough rights' to helpful message about admin permissions."""
        from domains.subscriptions.handlers import _get_actionable_telegram_error
        
        msg = _get_actionable_telegram_error('Bad Request: not enough rights')
        assert 'Add the bot to the channel' in msg or 'admin' in msg.lower()
    
    def test_bot_kicked_message(self):
        """Maps 'bot was kicked' to helpful message about re-adding bot."""
        from domains.subscriptions.handlers import _get_actionable_telegram_error
        
        msg = _get_actionable_telegram_error('Forbidden: bot was kicked')
        assert 'Re-add the bot' in msg or 'removed' in msg.lower()
    
    def test_unknown_error_preserved(self):
        """Unknown errors are preserved with prefix."""
        from domains.subscriptions.handlers import _get_actionable_telegram_error
        
        msg = _get_actionable_telegram_error('Some unknown Telegram error')
        assert 'Telegram error' in msg
        assert 'Some unknown Telegram error' in msg
