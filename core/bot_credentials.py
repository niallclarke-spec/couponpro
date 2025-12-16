"""
Bot Credential Resolver - Database-only credential retrieval for tenant bots.

This module provides the ONLY authorized way to retrieve bot credentials.
NO environment variable fallbacks are allowed - all credentials must come from the database.
"""
import db
from core.logging import get_logger

logger = get_logger(__name__)


class BotNotConfiguredError(Exception):
    """Raised when bot credentials are not found in the database for a tenant."""
    
    def __init__(self, tenant_id: str, bot_role: str):
        self.tenant_id = tenant_id
        self.bot_role = bot_role
        message = (
            f"Bot not configured: No '{bot_role}' bot found for tenant '{tenant_id}'. "
            f"Please configure the bot in the Connections settings."
        )
        super().__init__(message)


class BotCredentialResolver:
    """
    Resolves bot credentials from the database only.
    
    This is the single source of truth for bot credentials across all bot systems.
    No environment variable fallbacks are allowed.
    """
    
    def get_bot_credentials(self, tenant_id: str, bot_role: str) -> dict:
        """
        Retrieve bot credentials from the database.
        
        Args:
            tenant_id: The tenant ID to look up
            bot_role: The bot role ('signal' or 'message')
            
        Returns:
            dict with keys: bot_token, bot_username, channel_id, webhook_url
            
        Raises:
            BotNotConfiguredError: If no bot connection found for this tenant/role
        """
        connection = db.get_bot_connection(tenant_id, bot_role)
        
        if not connection:
            logger.warning(
                f"Bot credentials not found: tenant_id={tenant_id}, bot_role={bot_role}"
            )
            raise BotNotConfiguredError(tenant_id, bot_role)
        
        logger.info(
            f"Bot credentials retrieved: tenant_id={tenant_id}, "
            f"bot_role={bot_role}, bot_username={connection.get('bot_username')}"
        )
        
        return {
            'bot_token': connection.get('bot_token'),
            'bot_username': connection.get('bot_username'),
            'channel_id': connection.get('channel_id'),
            'webhook_url': connection.get('webhook_url'),
        }
    
    def get_signal_bot(self, tenant_id: str) -> dict:
        """
        Shorthand to get signal bot credentials.
        
        Args:
            tenant_id: The tenant ID
            
        Returns:
            dict with bot credentials
            
        Raises:
            BotNotConfiguredError: If signal bot not configured for tenant
        """
        return self.get_bot_credentials(tenant_id, 'signal')
    
    def get_message_bot(self, tenant_id: str) -> dict:
        """
        Shorthand to get message bot credentials.
        
        Args:
            tenant_id: The tenant ID
            
        Returns:
            dict with bot credentials
            
        Raises:
            BotNotConfiguredError: If message bot not configured for tenant
        """
        return self.get_bot_credentials(tenant_id, 'message')


def get_bot_credentials(tenant_id: str, bot_role: str) -> dict:
    """
    Module-level convenience function for retrieving bot credentials.
    
    Creates a BotCredentialResolver instance and calls get_bot_credentials.
    
    Args:
        tenant_id: The tenant ID to look up
        bot_role: The bot role ('signal' or 'message')
        
    Returns:
        dict with keys: bot_token, bot_username, channel_id, webhook_url
        
    Raises:
        BotNotConfiguredError: If no bot connection found for this tenant/role
    """
    resolver = BotCredentialResolver()
    return resolver.get_bot_credentials(tenant_id, bot_role)
