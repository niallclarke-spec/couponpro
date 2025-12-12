"""
Centralized configuration for server.py
All environment variable access should go through this Config class.
NO side effects at import time - no DB connections, no threads, no webhooks.
"""
import os


class Config:
    TEMPLATES_PATH = 'assets/templates'
    
    @staticmethod
    def get_port():
        return int(os.environ.get('PORT', 5000))
    
    @staticmethod
    def get_admin_password():
        return os.environ.get('ADMIN_PASSWORD')
    
    @staticmethod
    def get_forex_channel_id():
        return os.environ.get('FOREX_CHANNEL_ID')
    
    @staticmethod
    def get_forex_bot_token():
        return os.environ.get('FOREX_BOT_TOKEN') or os.environ.get('ENTRYLAB_TEST_BOT')
    
    @staticmethod
    def get_entrylab_api_key():
        return os.environ.get('ENTRYLAB_API_KEY', '')
    
    @staticmethod
    def get_app_url():
        return os.environ.get('APP_URL', '')
    
    @staticmethod
    def get_spaces_bucket():
        return os.environ.get('SPACES_BUCKET', 'couponpro-templates')
    
    @staticmethod
    def get_spaces_region():
        return os.environ.get('SPACES_REGION', 'lon1')
    
    @staticmethod
    def get_telegram_bot_token():
        return os.environ.get('TELEGRAM_BOT_TOKEN')
    
    @staticmethod
    def is_replit_deployment():
        return os.environ.get('REPLIT_DEPLOYMENT') == '1'
    
    @staticmethod
    def get_stripe_webhook_secret():
        return os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    @staticmethod
    def get_test_stripe_webhook_secret():
        return os.environ.get('TEST_STRIPE_WEBHOOK_SECRET') or os.environ.get('STRIPE_WEBHOOK_SECRET')
