"""
Tests for Cross Promo automation feature.
Covers: Mon-Fri gating, tenant isolation, dedupe, atomic claiming, failure handling.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytz


class TestWeekdayGating:
    """Test that cross promo only runs Monday-Friday."""
    
    def test_is_weekday_monday(self):
        """Monday should be a weekday."""
        from domains.crosspromo.service import is_weekday
        
        with patch('domains.crosspromo.service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 0  # Monday
            mock_dt.now.return_value = mock_now
            
            assert is_weekday('UTC') == True
    
    def test_is_weekday_friday(self):
        """Friday should be a weekday."""
        from domains.crosspromo.service import is_weekday
        
        with patch('domains.crosspromo.service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 4  # Friday
            mock_dt.now.return_value = mock_now
            
            assert is_weekday('UTC') == True
    
    def test_is_weekday_saturday(self):
        """Saturday should NOT be a weekday."""
        from domains.crosspromo.service import is_weekday
        
        with patch('domains.crosspromo.service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5  # Saturday
            mock_dt.now.return_value = mock_now
            
            assert is_weekday('UTC') == False
    
    def test_is_weekday_sunday(self):
        """Sunday should NOT be a weekday."""
        from domains.crosspromo.service import is_weekday
        
        with patch('domains.crosspromo.service.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 6  # Sunday
            mock_dt.now.return_value = mock_now
            
            assert is_weekday('UTC') == False


class TestMorningMessage:
    """Test morning message building."""
    
    def test_build_morning_message_no_news(self):
        """Morning message should work even without news."""
        from domains.crosspromo.service import build_morning_news_message
        
        with patch('domains.crosspromo.service.fetch_xau_news', return_value=[]):
            message = build_morning_news_message('test-tenant')
            
            # Returns just the summary (header added by forex_bot.py)
            assert 'Markets are quiet' in message
    
    def test_build_morning_message_with_news(self):
        """Morning message should include news items."""
        from domains.crosspromo.service import build_morning_news_message
        
        # Metals-API response format - only title field
        mock_news = [
            {'title': 'Fed rates decision'},
            {'title': 'Gold prices surge'}
        ]
        
        with patch('domains.crosspromo.service.fetch_xau_news', return_value=mock_news):
            message = build_morning_news_message('test-tenant')
            
            # Returns just the summary with headlines (header added by forex_bot.py)
            assert 'Fed rates decision' in message
            assert 'Gold prices surge' in message


class TestVIPSoonMessage:
    """Test VIP soon message."""
    
    def test_vip_soon_message(self):
        """VIP soon message should have expected content."""
        from domains.crosspromo.service import build_vip_soon_message
        
        message = build_vip_soon_message()
        
        assert 'signals' in message.lower() or 'vip' in message.lower()


class TestCTAMessage:
    """Test CTA message building."""
    
    def test_cta_message_includes_url(self):
        """CTA message should include the provided URL."""
        from domains.crosspromo.service import build_congrats_cta_message
        
        cta_url = 'https://entrylab.io/subscribe'
        message = build_congrats_cta_message(cta_url)
        
        assert cta_url in message
        assert 'Congrats' in message or 'VIP' in message
    
    def test_cta_message_html_link(self):
        """CTA message should include HTML link format."""
        from domains.crosspromo.service import build_congrats_cta_message
        
        cta_url = 'https://example.com/join'
        message = build_congrats_cta_message(cta_url)
        
        assert f'<a href="{cta_url}">' in message


class TestDeduplication:
    """Test job deduplication."""
    
    @patch('domains.crosspromo.repo.db')
    def test_dedupe_key_prevents_duplicates(self, mock_db):
        """Jobs with same dedupe key should not create duplicates."""
        from domains.crosspromo import repo
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No result means dedupe conflict
        mock_conn.cursor.return_value = mock_cursor
        mock_db.db_pool.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.db_pool.get_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        result = repo.enqueue_job(
            tenant_id='test-tenant',
            job_type='morning_news',
            run_at=datetime.utcnow(),
            dedupe_key='test-tenant|2024-01-15|morning_news'
        )
        
        assert result is None


class TestTenantIsolation:
    """Test that tenants cannot access each other's data."""
    
    def test_get_settings_returns_tenant_specific(self):
        """Settings should be tenant-specific."""
        from domains.crosspromo.handlers import handle_get_settings
        
        mock_handler = MagicMock()
        mock_handler.tenant_id = 'tenant-a'
        
        with patch('domains.crosspromo.handlers.repo.get_settings', return_value=None) as mock_get:
            handle_get_settings(mock_handler)
            
            mock_get.assert_called_once_with('tenant-a')


class TestJobExecution:
    """Test job execution logic."""
    
    def test_send_job_fails_without_settings(self):
        """Jobs should fail if settings not found."""
        from domains.crosspromo.service import send_job
        
        job = {'tenant_id': 'test', 'job_type': 'morning_news', 'payload': {}}
        
        with patch('domains.crosspromo.service.repo.get_settings', return_value=None):
            result = send_job(job)
            
            assert result['success'] == False
            assert 'not found' in result['error'].lower()
    
    def test_send_job_fails_if_disabled(self):
        """Jobs should fail if cross promo is disabled."""
        from domains.crosspromo.service import send_job
        
        job = {'tenant_id': 'test', 'job_type': 'morning_news', 'payload': {}}
        settings = {'enabled': False, 'free_channel_id': '-123'}
        
        with patch('domains.crosspromo.service.repo.get_settings', return_value=settings):
            result = send_job(job)
            
            assert result['success'] == False
            assert 'disabled' in result['error'].lower()
    
    def test_send_job_fails_without_channel(self):
        """Jobs should fail if free channel not configured."""
        from domains.crosspromo.service import send_job
        
        job = {'tenant_id': 'test', 'job_type': 'morning_news', 'payload': {}}
        settings = {'enabled': True, 'free_channel_id': None, 'bot_role': 'signal_bot'}
        
        with patch('domains.crosspromo.service.repo.get_settings', return_value=settings):
            result = send_job(job)
            
            assert result['success'] == False
            assert 'channel' in result['error'].lower()


class TestTelegramClient:
    """Test Telegram client functions."""
    
    @patch('integrations.telegram.client.requests.post')
    def test_send_message_success(self, mock_post):
        """send_message should handle successful response."""
        from integrations.telegram.client import send_message
        
        mock_post.return_value.json.return_value = {'ok': True}
        
        result = send_message('bot-token', '-123', 'Hello!')
        
        assert result['success'] == True
        mock_post.assert_called_once()
    
    @patch('integrations.telegram.client.requests.post')
    def test_send_message_failure(self, mock_post):
        """send_message should handle error response."""
        from integrations.telegram.client import send_message
        
        mock_post.return_value.json.return_value = {'ok': False, 'description': 'Chat not found'}
        
        result = send_message('bot-token', '-123', 'Hello!')
        
        assert result['success'] == False
        assert 'Chat not found' in result['error']
    
    @patch('integrations.telegram.client.requests.post')
    def test_copy_message_falls_back_to_forward(self, mock_post):
        """copy_message should fallback to forward_message on failure."""
        from integrations.telegram.client import copy_message
        
        mock_post.return_value.json.side_effect = [
            {'ok': False, 'description': 'copyMessage not supported'},
            {'ok': True}  # forwardMessage succeeds
        ]
        
        result = copy_message('bot-token', '-123', '-456', 999)
        
        assert result['success'] == True
        assert mock_post.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
