#!/usr/bin/env python3
"""
One-time seed script to migrate EntryLab tokens from environment variables to the database.

This script reads TELEGRAM_BOT_TOKEN and FOREX_BOT_TOKEN/FOREX_CHANNEL_ID from the environment
and inserts them into the tenant_bot_connections table for tenant_id='entrylab'.

Usage:
    python scripts/seed_entrylab_bots.py

The script is idempotent - safe to run multiple times.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from core.config import Config
import db


TENANT_ID = 'entrylab'
TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/getMe'


def validate_telegram_token(token: str) -> dict | None:
    """
    Validate a Telegram bot token by calling the getMe API.
    
    Args:
        token: Telegram bot token
        
    Returns:
        Bot info dict if valid, None if invalid
    """
    if not token:
        return None
    
    try:
        response = requests.get(TELEGRAM_API_URL.format(token=token), timeout=10)
        data = response.json()
        
        if data.get('ok') and data.get('result'):
            return data['result']
        else:
            print(f"  [ERROR] Telegram API returned: {data.get('description', 'Unknown error')}")
            return None
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to validate token: {e}")
        return None


def seed_message_bot() -> bool:
    """
    Seed the message bot (TELEGRAM_BOT_TOKEN) for EntryLab.
    
    Returns:
        True if successful or already exists, False on failure
    """
    print("\n[MESSAGE BOT] Processing...")
    
    token = Config.get_telegram_bot_token()
    if not token:
        print("  [SKIP] TELEGRAM_BOT_TOKEN not set in environment")
        return False
    
    existing = db.get_bot_connection(TENANT_ID, 'message')
    if existing and existing.get('bot_token'):
        print(f"  [EXISTS] Message bot already configured: @{existing.get('bot_username', 'unknown')}")
        print(f"           Last validated: {existing.get('last_validated_at', 'never')}")
        return True
    
    print("  [VALIDATE] Checking token with Telegram API...")
    bot_info = validate_telegram_token(token)
    if not bot_info:
        print("  [FAILED] Token validation failed - not inserting into database")
        return False
    
    bot_username = bot_info.get('username', '')
    print(f"  [VALID] Token is valid for bot: @{bot_username}")
    
    success = db.upsert_bot_connection(
        tenant_id=TENANT_ID,
        bot_role='message',
        bot_token=token,
        bot_username=bot_username
    )
    
    if success:
        print(f"  [SUCCESS] Message bot @{bot_username} saved for tenant '{TENANT_ID}'")
    else:
        print("  [FAILED] Database insert failed")
    
    return success


def seed_signal_bot() -> bool:
    """
    Seed the signal bot (FOREX_BOT_TOKEN + FOREX_CHANNEL_ID) for EntryLab.
    
    Returns:
        True if successful or already exists, False on failure
    """
    print("\n[SIGNAL BOT] Processing...")
    
    token = Config.get_forex_bot_token()
    channel_id = Config.get_forex_channel_id()
    
    if not token:
        print("  [SKIP] FOREX_BOT_TOKEN not set in environment")
        return False
    
    existing = db.get_bot_connection(TENANT_ID, 'signal')
    if existing and existing.get('bot_token'):
        print(f"  [EXISTS] Signal bot already configured: @{existing.get('bot_username', 'unknown')}")
        print(f"           Channel ID: {existing.get('channel_id', 'not set')}")
        print(f"           Last validated: {existing.get('last_validated_at', 'never')}")
        return True
    
    print("  [VALIDATE] Checking token with Telegram API...")
    bot_info = validate_telegram_token(token)
    if not bot_info:
        print("  [FAILED] Token validation failed - not inserting into database")
        return False
    
    bot_username = bot_info.get('username', '')
    print(f"  [VALID] Token is valid for bot: @{bot_username}")
    
    if channel_id:
        print(f"  [INFO] Channel ID: {channel_id}")
    else:
        print("  [WARN] FOREX_CHANNEL_ID not set - signal bot will not be able to post to channel")
    
    success = db.upsert_bot_connection(
        tenant_id=TENANT_ID,
        bot_role='signal',
        bot_token=token,
        bot_username=bot_username,
        channel_id=channel_id
    )
    
    if success:
        print(f"  [SUCCESS] Signal bot @{bot_username} saved for tenant '{TENANT_ID}'")
    else:
        print("  [FAILED] Database insert failed")
    
    return success


def main():
    """Main entry point for the seed script."""
    print("=" * 60)
    print("EntryLab Bot Credentials Seed Script")
    print("=" * 60)
    print(f"Target tenant: {TENANT_ID}")
    
    if not db.db_pool or not db.db_pool.connection_pool:
        print("\n[ERROR] Database not initialized. Cannot proceed.")
        sys.exit(1)
    
    results = {
        'message_bot': seed_message_bot(),
        'signal_bot': seed_signal_bot()
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_success = True
    for bot_type, success in results.items():
        status = "✓ OK" if success else "✗ FAILED/SKIPPED"
        print(f"  {bot_type}: {status}")
        if not success:
            all_success = False
    
    if all_success:
        print("\n[DONE] All bot credentials seeded successfully!")
    else:
        print("\n[DONE] Some bot credentials were not seeded (see above for details)")
    
    sys.exit(0 if all_success else 1)


if __name__ == '__main__':
    main()
