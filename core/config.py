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
    
    @staticmethod
    def get_database_url():
        return os.environ.get('DATABASE_URL')
    
    @staticmethod
    def get_db_host():
        return os.environ.get('DB_HOST')
    
    @staticmethod
    def get_db_port():
        return os.environ.get('DB_PORT')
    
    @staticmethod
    def get_db_name():
        return os.environ.get('DB_NAME')
    
    @staticmethod
    def get_db_user():
        return os.environ.get('DB_USER')
    
    @staticmethod
    def get_db_password():
        return os.environ.get('DB_PASSWORD')
    
    @staticmethod
    def get_db_sslmode():
        return os.environ.get('DB_SSLMODE', 'require')
    
    @staticmethod
    def get_stripe_secret_key():
        return os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET')
    
    @staticmethod
    def get_stripe_publishable_key():
        return os.environ.get('STRIPE_PUBLISHABLE_KEY')
    
    @staticmethod
    def get_test_stripe_secret():
        return os.environ.get('TEST_STRIPE_SECRET')
    
    @staticmethod
    def get_test_stripe_publishable_key():
        return os.environ.get('TEST_STRIPE_PUBLISHABLE_KEY')
    
    @staticmethod
    def get_spaces_access_key():
        return os.environ.get('SPACES_ACCESS_KEY')
    
    @staticmethod
    def get_spaces_secret_key():
        return os.environ.get('SPACES_SECRET_KEY')
    
    @staticmethod
    def get_twelve_data_api_key():
        return os.environ.get('TWELVE_DATA_API_KEY')
    
    @staticmethod
    def get_funderpro_product_id():
        return os.environ.get('FUNDERPRO_PRODUCT_ID')
    
    @staticmethod
    def get_replit_connectors_hostname():
        return os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    
    @staticmethod
    def get_repl_identity():
        return os.environ.get('REPL_IDENTITY')
    
    @staticmethod
    def get_web_repl_renewal():
        return os.environ.get('WEB_REPL_RENEWAL')
    
    @staticmethod
    def get_clerk_publishable_key():
        """Matches DigitalOcean + Clerk naming convention (NEXT_PUBLIC_ prefix)."""
        return os.environ.get('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY')
    
    @staticmethod
    def get_clerk_jwks_url():
        """
        Get Clerk JWKS URL for runtime key fetching.
        Format: https://<your-clerk-domain>/.well-known/jwks.json
        """
        return os.environ.get('CLERK_JWKS_URL')
