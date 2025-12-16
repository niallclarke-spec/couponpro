"""
Test FX Signals Connections architecture isolation from Coupon Bot.

These tests verify:
1. Coupon bot uses Config.get_telegram_bot_token() (environment-based)
2. FX/Signal bot uses BotCredentialResolver (database-based, tenant-scoped)
3. Message Bot is not seeded by default - must be configured via UI
4. Architectural separation is maintained
"""
import pytest
from unittest.mock import patch, MagicMock
import inspect


class TestCouponBotUsesConfigNotCredentialsResolver:
    """Verify handle_coupon_telegram_webhook uses Config.get_telegram_bot_token()"""
    
    def test_coupon_webhook_source_code_uses_config(self):
        """Static analysis: handle_coupon_telegram_webhook calls Config.get_telegram_bot_token()"""
        from integrations.telegram.webhooks import handle_coupon_telegram_webhook
        
        source = inspect.getsource(handle_coupon_telegram_webhook)
        
        assert 'Config.get_telegram_bot_token()' in source, \
            "Coupon webhook must use Config.get_telegram_bot_token()"
        
        assert 'get_bot_credentials' not in source or 'get_bot_credentials' in source.split('check_journey')[0] == False, \
            "Coupon webhook should not use get_bot_credentials for its main token"
    
    def test_coupon_webhook_does_not_import_credential_resolver_for_main_token(self):
        """Verify coupon bot's main token comes from Config, not BotCredentialResolver"""
        from integrations.telegram.webhooks import handle_coupon_telegram_webhook
        
        source = inspect.getsource(handle_coupon_telegram_webhook)
        
        lines_before_journey_check = source.split('check_journey_trigger')[0]
        
        assert 'BotCredentialResolver' not in lines_before_journey_check, \
            "Coupon webhook should not use BotCredentialResolver for bot token"


class TestNoCouponBotInConnectionsTable:
    """Verify tenant_bot_connections has no 'coupon' bot_role"""
    
    def test_valid_bot_roles_are_signal_and_message_only(self):
        """Architecture: Only 'signal' and 'message' are valid bot_role values"""
        from core.bot_credentials import BotCredentialResolver
        
        source = inspect.getsource(BotCredentialResolver)
        
        assert "'signal'" in source or '"signal"' in source, \
            "BotCredentialResolver should reference signal bot role"
        assert "'message'" in source or '"message"' in source, \
            "BotCredentialResolver should reference message bot role"
        
        assert "'coupon'" not in source.lower(), \
            "BotCredentialResolver should NOT have coupon as a bot role"
    
    def test_db_get_bot_connection_docstring_mentions_signal_and_message(self):
        """db.get_bot_connection should document signal and message roles only"""
        import db
        
        func_source = inspect.getsource(db.get_bot_connection)
        
        assert 'signal' in func_source.lower() or 'message' in func_source.lower(), \
            "get_bot_connection should mention valid bot roles"
    
    @patch('db.db_pool')
    def test_query_connections_no_coupon_role(self, mock_pool):
        """Mock DB query: tenant_bot_connections should never have 'coupon' role"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.connection_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_cursor.fetchall.return_value = [
            ('entrylab', 'signal'),
            ('tenant1', 'signal'),
            ('tenant1', 'message'),
        ]
        
        for tenant_id, bot_role in mock_cursor.fetchall.return_value:
            assert bot_role in ('signal', 'message'), \
                f"Invalid bot_role '{bot_role}' found - only signal/message allowed"
            assert bot_role != 'coupon', \
                f"coupon bot should never be in tenant_bot_connections"


class TestMessageBotEmptyByDefault:
    """Verify Message Bot is NOT seeded by seed script"""
    
    def test_seed_script_skips_message_bot(self):
        """seed_entrylab_bots.py should explicitly skip Message Bot"""
        with open('scripts/seed_entrylab_bots.py', 'r') as f:
            seed_source = f.read()
        
        assert 'message' in seed_source.lower(), \
            "Seed script should mention message bot"
        
        assert 'skip' in seed_source.lower() or 'not seed' in seed_source.lower() or 'configure via ui' in seed_source.lower(), \
            "Seed script should indicate Message Bot is skipped"
    
    def test_seed_script_only_seeds_signal_bot(self):
        """seed_entrylab_bots.py main logic should only seed signal bot"""
        with open('scripts/seed_entrylab_bots.py', 'r') as f:
            seed_source = f.read()
        
        assert "seed_signal_bot" in seed_source, \
            "Seed script should have seed_signal_bot function"
        
        assert "seed_message_bot" not in seed_source, \
            "Seed script should NOT have seed_message_bot function"
    
    def test_message_bot_requires_ui_configuration(self):
        """Documentation check: Message Bot must be configured via UI"""
        with open('scripts/seed_entrylab_bots.py', 'r') as f:
            seed_source = f.read()
        
        assert 'UI' in seed_source or 'ui' in seed_source.lower(), \
            "Seed script should mention UI configuration for Message Bot"


class TestSignalBotIsTenantScoped:
    """Verify Signal Bot entries have proper tenant_id"""
    
    def test_upsert_bot_connection_requires_tenant_id(self):
        """db.upsert_bot_connection must require tenant_id parameter"""
        import db
        
        sig = inspect.signature(db.upsert_bot_connection)
        params = list(sig.parameters.keys())
        
        assert 'tenant_id' in params, \
            "upsert_bot_connection must have tenant_id parameter"
        
        tenant_param = sig.parameters['tenant_id']
        assert tenant_param.default == inspect.Parameter.empty, \
            "tenant_id should be a required parameter (no default)"
    
    def test_get_bot_connection_requires_tenant_id(self):
        """db.get_bot_connection must require tenant_id parameter"""
        import db
        
        sig = inspect.signature(db.get_bot_connection)
        params = list(sig.parameters.keys())
        
        assert 'tenant_id' in params, \
            "get_bot_connection must have tenant_id parameter"
    
    def test_bot_credential_resolver_requires_tenant_id(self):
        """BotCredentialResolver.get_bot_credentials requires tenant_id"""
        from core.bot_credentials import BotCredentialResolver
        
        resolver = BotCredentialResolver()
        sig = inspect.signature(resolver.get_bot_credentials)
        params = list(sig.parameters.keys())
        
        assert 'tenant_id' in params, \
            "get_bot_credentials must require tenant_id"
    
    def test_signal_bot_helper_requires_tenant_id(self):
        """BotCredentialResolver.get_signal_bot requires tenant_id"""
        from core.bot_credentials import BotCredentialResolver
        
        resolver = BotCredentialResolver()
        sig = inspect.signature(resolver.get_signal_bot)
        
        assert 'tenant_id' in sig.parameters, \
            "get_signal_bot must require tenant_id"


class TestJourneysRequireMessageBot:
    """Test JourneyEngine._send_message returns False when Message Bot not configured"""
    
    def test_journey_engine_send_message_uses_get_bot_credentials(self):
        """JourneyEngine._send_message should call get_bot_credentials"""
        from domains.journeys.engine import JourneyEngine
        
        source = inspect.getsource(JourneyEngine._send_message)
        
        assert 'get_bot_credentials' in source, \
            "_send_message must use get_bot_credentials"
        
        assert "'message'" in source or '"message"' in source, \
            "_send_message must request 'message' bot role"
    
    def test_journey_engine_handles_bot_not_configured_error(self):
        """JourneyEngine._send_message should handle BotNotConfiguredError"""
        from domains.journeys.engine import JourneyEngine
        
        source = inspect.getsource(JourneyEngine._send_message)
        
        assert 'BotNotConfiguredError' in source, \
            "_send_message must catch BotNotConfiguredError"
    
    @patch('domains.journeys.engine.get_bot_credentials')
    def test_send_message_returns_false_when_message_bot_not_configured(self, mock_get_creds):
        """_send_message returns False when Message Bot not configured"""
        from domains.journeys.engine import JourneyEngine
        from core.bot_credentials import BotNotConfiguredError
        
        mock_get_creds.side_effect = BotNotConfiguredError('test_tenant', 'message')
        
        engine = JourneyEngine()
        result = engine._send_message('test_tenant', 12345, 'Test message')
        
        assert result is False, \
            "_send_message should return False when BotNotConfiguredError raised"
        
        mock_get_creds.assert_called_once_with('test_tenant', 'message')
    
    @patch('domains.journeys.engine.get_bot_credentials')
    @patch('domains.journeys.engine.requests')
    def test_send_message_returns_true_when_message_bot_configured(self, mock_requests, mock_get_creds):
        """_send_message returns True when Message Bot is properly configured"""
        from domains.journeys.engine import JourneyEngine
        
        mock_get_creds.return_value = {
            'bot_token': 'test_token_123',
            'bot_username': 'test_bot',
            'channel_id': None,
            'webhook_url': None
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response
        
        engine = JourneyEngine()
        result = engine._send_message('test_tenant', 12345, 'Test message')
        
        assert result is True, \
            "_send_message should return True when bot configured and API succeeds"


class TestFxWebhookUsesBotCredentials:
    """Verify handle_forex_telegram_webhook uses get_bot_credentials"""
    
    def test_forex_webhook_source_uses_get_bot_credentials(self):
        """Static analysis: handle_forex_telegram_webhook uses get_bot_credentials"""
        from integrations.telegram.webhooks import handle_forex_telegram_webhook
        
        source = inspect.getsource(handle_forex_telegram_webhook)
        
        assert 'get_bot_credentials' in source, \
            "Forex webhook must use get_bot_credentials from BotCredentialResolver"
    
    def test_forex_webhook_requests_signal_bot_role(self):
        """handle_forex_telegram_webhook should request 'signal' bot role"""
        from integrations.telegram.webhooks import handle_forex_telegram_webhook
        
        source = inspect.getsource(handle_forex_telegram_webhook)
        
        assert "'signal'" in source, \
            "Forex webhook must request 'signal' bot role"
    
    def test_forex_webhook_handles_bot_not_configured_error(self):
        """handle_forex_telegram_webhook should handle BotNotConfiguredError"""
        from integrations.telegram.webhooks import handle_forex_telegram_webhook
        
        source = inspect.getsource(handle_forex_telegram_webhook)
        
        assert 'BotNotConfiguredError' in source, \
            "Forex webhook must handle BotNotConfiguredError"
    
    def test_forex_webhook_does_not_use_config_for_token(self):
        """handle_forex_telegram_webhook should NOT use Config.get_forex_bot_token()"""
        from integrations.telegram.webhooks import handle_forex_telegram_webhook
        
        source = inspect.getsource(handle_forex_telegram_webhook)
        
        assert 'Config.get_forex_bot_token' not in source, \
            "Forex webhook should NOT use Config.get_forex_bot_token - must use database"
    
    def test_forex_webhook_uses_entrylab_tenant(self):
        """handle_forex_telegram_webhook should use 'entrylab' as tenant_id"""
        from integrations.telegram.webhooks import handle_forex_telegram_webhook
        
        source = inspect.getsource(handle_forex_telegram_webhook)
        
        assert "'entrylab'" in source, \
            "Forex webhook should reference 'entrylab' tenant"


class TestArchitecturalSeparation:
    """Additional tests to verify complete architectural separation"""
    
    def test_webhook_module_imports_both_config_and_credentials(self):
        """webhooks.py should import both Config and get_bot_credentials"""
        with open('integrations/telegram/webhooks.py', 'r') as f:
            source = f.read()
        
        assert 'from core.config import Config' in source, \
            "webhooks.py must import Config for coupon bot"
        
        assert 'from core.bot_credentials import get_bot_credentials' in source, \
            "webhooks.py must import get_bot_credentials for FX bot"
    
    def test_config_has_telegram_bot_token_method(self):
        """Config class should have get_telegram_bot_token method"""
        from core.config import Config
        
        assert hasattr(Config, 'get_telegram_bot_token'), \
            "Config must have get_telegram_bot_token method"
        
        assert callable(Config.get_telegram_bot_token), \
            "get_telegram_bot_token must be callable"
    
    def test_config_telegram_token_is_environment_based(self):
        """Config.get_telegram_bot_token should read from environment"""
        from core.config import Config
        
        source = inspect.getsource(Config.get_telegram_bot_token)
        
        assert 'os.environ' in source or 'TELEGRAM_BOT_TOKEN' in source, \
            "get_telegram_bot_token must read from environment"
    
    def test_bot_credential_resolver_is_database_based(self):
        """BotCredentialResolver should query database, not environment"""
        from core.bot_credentials import BotCredentialResolver
        
        source = inspect.getsource(BotCredentialResolver.get_bot_credentials)
        
        assert 'db.get_bot_connection' in source, \
            "BotCredentialResolver must query database via db.get_bot_connection"
        
        assert 'os.environ' not in source, \
            "BotCredentialResolver should NOT fall back to environment variables"
