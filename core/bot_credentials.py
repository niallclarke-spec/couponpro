"""
Bot Credential Resolver - Database-only credential retrieval for tenant bots.

This module provides the ONLY authorized way to retrieve bot credentials.
NO environment variable fallbacks are allowed - all credentials must come from the database.
"""
import db
from core.logging import get_logger

logger = get_logger(__name__)

# Canonical bot role constants - these are the ONLY valid roles
SIGNAL_BOT = "signal_bot"
MESSAGE_BOT = "message_bot"

# Valid canonical roles
VALID_BOT_ROLES = {SIGNAL_BOT, MESSAGE_BOT}

# Legacy alias mapping for backward compatibility during migration
# Maps legacy role names to canonical names
LEGACY_ROLE_ALIASES = {
    "signal": SIGNAL_BOT,
    "message": MESSAGE_BOT,
}


def normalize_bot_role(bot_role: str) -> tuple:
    """
    Normalize a bot role to its canonical form.
    
    Args:
        bot_role: The bot role string (may be legacy or canonical)
        
    Returns:
        tuple of (canonical_role, was_legacy_alias)
    """
    if bot_role in VALID_BOT_ROLES:
        return bot_role, False
    
    if bot_role in LEGACY_ROLE_ALIASES:
        canonical = LEGACY_ROLE_ALIASES[bot_role]
        logger.warning(
            f"Legacy bot_role '{bot_role}' used, mapped to '{canonical}'. "
            f"Please update to use canonical role names."
        )
        return canonical, True
    
    return bot_role, False


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
            bot_role: The bot role ('signal_bot' or 'message_bot')
            
        Returns:
            dict with keys: bot_token, bot_username, channel_id, webhook_url, vip_channel_id, free_channel_id
            
        Raises:
            BotNotConfiguredError: If no bot connection found for this tenant/role
        """
        canonical_role, was_legacy = normalize_bot_role(bot_role)
        
        connection = db.get_bot_connection(tenant_id, canonical_role)
        
        if not connection and was_legacy:
            connection = db.get_bot_connection(tenant_id, bot_role)
        
        if not connection:
            logger.warning(
                f"Bot credentials not found: tenant_id={tenant_id}, bot_role={canonical_role}"
            )
            raise BotNotConfiguredError(tenant_id, canonical_role)
        
        logger.info(
            f"Bot credentials retrieved: tenant_id={tenant_id}, "
            f"bot_role={bot_role}, bot_username={connection.get('bot_username')}"
        )
        
        return {
            'bot_token': connection.get('bot_token'),
            'bot_username': connection.get('bot_username'),
            'channel_id': connection.get('channel_id'),
            'webhook_url': connection.get('webhook_url'),
            'vip_channel_id': connection.get('vip_channel_id'),
            'free_channel_id': connection.get('free_channel_id'),
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
        return self.get_bot_credentials(tenant_id, SIGNAL_BOT)
    
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
        return self.get_bot_credentials(tenant_id, MESSAGE_BOT)


def get_bot_credentials(tenant_id: str, bot_role: str) -> dict:
    """
    Module-level convenience function for retrieving bot credentials.
    
    Creates a BotCredentialResolver instance and calls get_bot_credentials.
    
    Args:
        tenant_id: The tenant ID to look up
        bot_role: The bot role ('signal_bot' or 'message_bot')
            Legacy 'signal' and 'message' are also accepted for backward compatibility
        
    Returns:
        dict with keys: bot_token, bot_username, channel_id, webhook_url
        
    Raises:
        BotNotConfiguredError: If no bot connection found for this tenant/role
    """
    resolver = BotCredentialResolver()
    return resolver.get_bot_credentials(tenant_id, bot_role)
