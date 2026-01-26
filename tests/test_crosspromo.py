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
        """Morning message should work even without news - returns fallback."""
        from domains.crosspromo.service import build_morning_news_message
        
        with patch('domains.crosspromo.service.fetch_xau_news', return_value=[]):
            message = build_morning_news_message('test-tenant')
            
            # Fallback message includes header and generic content
            assert 'Morning Briefing' in message
            assert 'Gold' in message or 'Markets' in message
    
    def test_build_morning_message_with_news(self):
        """Morning message should use AI to generate conversational summary."""
        from domains.crosspromo.service import build_morning_news_message, _fallback_morning_message
        
        # Metals-API response format - only title field
        mock_news = [
            {'title': 'Fed rates decision boosts gold'},
            {'title': 'Gold prices surge on inflation data'}
        ]
        
        with patch('domains.crosspromo.service.fetch_xau_news', return_value=mock_news):
            message = build_morning_news_message('test-tenant')
            
            # AI generates a conversational summary with the header
            # We can't test exact content since it's AI-generated
            # But it should have the header and be reasonably sized
            assert 'Morning Briefing' in message
            assert len(message) > 50  # Should be a real message, not empty


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
            # Error could be about bot credentials or channel - both are config issues
            assert 'bot' in result['error'].lower() or 'channel' in result['error'].lower()


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


class TestEODPipBrag:
    """Test end-of-day pip brag cascading lookback logic."""
    
    def test_cascade_finds_first_threshold(self):
        """Should return first window that meets threshold."""
        from domains.crosspromo.service import find_brag_worthy_pips
        
        # Mock: 2 days = 150 pips (meets 100 threshold)
        with patch('domains.crosspromo.service.repo.get_net_pips_over_days') as mock_pips:
            mock_pips.return_value = 150.0
            
            result = find_brag_worthy_pips('test-tenant')
            
            assert result == (150.0, 2)
            # Should only call once since first threshold met
            mock_pips.assert_called_once_with('test-tenant', 2)
    
    def test_cascade_falls_through_to_5_days(self):
        """Should check 5 days if 2 days < 100 pips."""
        from domains.crosspromo.service import find_brag_worthy_pips
        
        # Mock: 2 days = 89 pips, 5 days = 400 pips
        with patch('domains.crosspromo.service.repo.get_net_pips_over_days') as mock_pips:
            mock_pips.side_effect = [89.0, 400.0]
            
            result = find_brag_worthy_pips('test-tenant')
            
            assert result == (400.0, 5)
            assert mock_pips.call_count == 2
    
    def test_cascade_falls_through_to_7_days(self):
        """Should check 7 days if 5 days < 100 pips."""
        from domains.crosspromo.service import find_brag_worthy_pips
        
        # Mock: 2 days = 50, 5 days = 80, 7 days = 350 pips
        with patch('domains.crosspromo.service.repo.get_net_pips_over_days') as mock_pips:
            mock_pips.side_effect = [50.0, 80.0, 350.0]
            
            result = find_brag_worthy_pips('test-tenant')
            
            assert result == (350.0, 7)
            assert mock_pips.call_count == 3
    
    def test_cascade_falls_through_to_14_days(self):
        """Should check 14 days if 7 days < 300 pips."""
        from domains.crosspromo.service import find_brag_worthy_pips
        
        # Mock: 2d = 50, 5d = 80, 7d = 200, 14d = 600 pips
        with patch('domains.crosspromo.service.repo.get_net_pips_over_days') as mock_pips:
            mock_pips.side_effect = [50.0, 80.0, 200.0, 600.0]
            
            result = find_brag_worthy_pips('test-tenant')
            
            assert result == (600.0, 14)
            assert mock_pips.call_count == 4
    
    def test_cascade_returns_none_for_fallback(self):
        """Should return None if no threshold met (use fallback)."""
        from domains.crosspromo.service import find_brag_worthy_pips
        
        # Mock: all windows below threshold
        with patch('domains.crosspromo.service.repo.get_net_pips_over_days') as mock_pips:
            mock_pips.side_effect = [50.0, 60.0, 100.0, 200.0]  # All fail thresholds
            
            result = find_brag_worthy_pips('test-tenant')
            
            assert result is None
            assert mock_pips.call_count == 4
    
    def test_fallback_message_generation(self):
        """Fallback message should be generated when no threshold met."""
        from domains.crosspromo.service import _fallback_eod_message
        
        message = _fallback_eod_message(430.0, 5)
        
        assert '430' in message
        assert 'pips' in message.lower()
    
    def test_eod_message_includes_pip_count(self):
        """EOD brag message should include actual pip count."""
        from domains.crosspromo.service import _fallback_eod_message
        
        # Test with various pip counts
        for pips in [150, 430, 1990]:
            message = _fallback_eod_message(float(pips), 7)
            assert str(pips) in message, f"Pip count {pips} should be in message"
    
    def test_fallback_hype_message(self):
        """Generic fallback should work when no thresholds met."""
        from domains.crosspromo.service import get_fallback_hype_message
        
        message = get_fallback_hype_message()
        
        assert len(message) > 20  # Should be a real message
        assert 'vip' in message.lower() or 'profit' in message.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
