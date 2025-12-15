"""
Tenant-aware Stripe client helper.
Supports both direct API keys and Stripe Connect.
"""
import os
from core.logging import get_logger

logger = get_logger(__name__)


class TenantStripeClient:
    """Stripe client configured for a specific tenant."""
    
    def __init__(self, tenant_id: str, secret_key: str = None, stripe_account_id: str = None):
        self.tenant_id = tenant_id
        self.secret_key = secret_key
        self.stripe_account_id = stripe_account_id
        self._stripe = None
    
    @property
    def stripe(self):
        """Lazy-load Stripe module."""
        if self._stripe is None:
            import stripe
            self._stripe = stripe
            if self.secret_key:
                self._stripe.api_key = self.secret_key
        return self._stripe
    
    def list_products(self, active_only=True):
        """Fetch all products from tenant's Stripe account."""
        try:
            params = {'limit': 100}
            if active_only:
                params['active'] = True
            
            products = []
            has_more = True
            starting_after = None
            
            while has_more:
                if starting_after:
                    params['starting_after'] = starting_after
                
                if self.stripe_account_id:
                    result = self.stripe.Product.list(**params, stripe_account=self.stripe_account_id)
                else:
                    result = self.stripe.Product.list(**params)
                
                products.extend(result.data)
                has_more = result.has_more
                if has_more and result.data:
                    starting_after = result.data[-1].id
            
            return products, None
        except Exception as e:
            logger.exception(f"Error fetching products for tenant {self.tenant_id}")
            return None, str(e)
    
    def list_prices(self, active_only=True):
        """Fetch all prices from tenant's Stripe account."""
        try:
            params = {'limit': 100, 'expand': ['data.product']}
            if active_only:
                params['active'] = True
            
            prices = []
            has_more = True
            starting_after = None
            
            while has_more:
                if starting_after:
                    params['starting_after'] = starting_after
                
                if self.stripe_account_id:
                    result = self.stripe.Price.list(**params, stripe_account=self.stripe_account_id)
                else:
                    result = self.stripe.Price.list(**params)
                
                prices.extend(result.data)
                has_more = result.has_more
                if has_more and result.data:
                    starting_after = result.data[-1].id
            
            return prices, None
        except Exception as e:
            logger.exception(f"Error fetching prices for tenant {self.tenant_id}")
            return None, str(e)
    
    def get_subscription(self, subscription_id: str):
        """Get subscription details."""
        try:
            if self.stripe_account_id:
                return self.stripe.Subscription.retrieve(subscription_id, stripe_account=self.stripe_account_id), None
            return self.stripe.Subscription.retrieve(subscription_id), None
        except Exception as e:
            return None, str(e)


def get_tenant_stripe_client(tenant_id: str):
    """
    Get a configured Stripe client for a tenant.
    
    Returns (TenantStripeClient, error_message) tuple.
    """
    from core.tenant_credentials import resolve_credentials
    
    if tenant_id == 'entrylab':
        secret_key = os.environ.get('STRIPE_SECRET_KEY')
        if not secret_key:
            return None, "Stripe not configured for EntryLab"
        return TenantStripeClient(tenant_id, secret_key=secret_key), None
    
    creds = resolve_credentials(tenant_id, 'stripe')
    if not creds:
        return None, "Stripe not connected"
    
    secret_key = creds.get('secret_key')
    stripe_account_id = creds.get('stripe_connect_account_id')
    
    if not secret_key and not stripe_account_id:
        return None, "Stripe not connected"
    
    if stripe_account_id and not secret_key:
        platform_key = os.environ.get('STRIPE_SECRET_KEY')
        if not platform_key:
            return None, "Platform Stripe key not configured"
        return TenantStripeClient(tenant_id, secret_key=platform_key, stripe_account_id=stripe_account_id), None
    
    return TenantStripeClient(tenant_id, secret_key=secret_key, stripe_account_id=stripe_account_id), None
