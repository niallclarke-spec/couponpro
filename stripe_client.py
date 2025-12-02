"""
Stripe Client for Python
Fetches credentials from Replit connection API and provides Stripe access
"""
import os
import stripe
import requests
from datetime import datetime

_stripe_credentials = None

def get_stripe_credentials():
    """
    Fetch Stripe credentials - tries Replit connector first, then falls back to env vars
    
    Supports:
    1. Replit Stripe Connector (preferred)
    2. Manual env vars: STRIPE_SECRET_KEY/STRIPE_SECRET + STRIPE_PUBLISHABLE_KEY
    """
    global _stripe_credentials
    
    if _stripe_credentials:
        return _stripe_credentials
    
    # First, try to get from manual environment variables (fallback)
    manual_secret = os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET')
    manual_publishable = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    
    # Try Replit connector API first
    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    
    if hostname:
        try:
            repl_identity = os.environ.get('REPL_IDENTITY')
            web_repl_renewal = os.environ.get('WEB_REPL_RENEWAL')
            
            if repl_identity:
                x_replit_token = f'repl {repl_identity}'
            elif web_repl_renewal:
                x_replit_token = f'depl {web_repl_renewal}'
            else:
                raise Exception('X_REPLIT_TOKEN not found for repl/depl')
            
            is_production = os.environ.get('REPLIT_DEPLOYMENT') == '1'
            target_environment = 'production' if is_production else 'development'
            
            url = f'https://{hostname}/api/v2/connection'
            params = {
                'include_secrets': 'true',
                'connector_names': 'stripe',
                'environment': target_environment
            }
            
            response = requests.get(url, params=params, headers={
                'Accept': 'application/json',
                'X_REPLIT_TOKEN': x_replit_token
            })
            
            data = response.json()
            connection = data.get('items', [{}])[0] if data.get('items') else {}
            settings = connection.get('settings', {})
            
            if settings.get('publishable') and settings.get('secret'):
                print(f"[STRIPE] Using Replit connector credentials ({target_environment})")
                _stripe_credentials = {
                    'publishable_key': settings['publishable'],
                    'secret_key': settings['secret']
                }
                return _stripe_credentials
        except Exception as e:
            print(f"[STRIPE] Replit connector failed: {e}, trying manual env vars...")
    
    # Fall back to manual environment variables
    if manual_secret and manual_publishable:
        print("[STRIPE] Using manual environment variables (STRIPE_SECRET_KEY/STRIPE_PUBLISHABLE_KEY)")
        _stripe_credentials = {
            'publishable_key': manual_publishable,
            'secret_key': manual_secret
        }
        return _stripe_credentials
    
    # Neither worked
    raise Exception('Stripe credentials not found. Set up Replit Stripe connector or add STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY environment variables.')

def get_stripe_client():
    """Get configured Stripe client"""
    credentials = get_stripe_credentials()
    stripe.api_key = credentials['secret_key']
    return stripe

def get_subscription_billing_info(stripe_subscription_id):
    """
    Fetch complete billing information for a subscription from Stripe
    Returns dict with billing details or None if not found
    """
    if not stripe_subscription_id:
        return None
    
    try:
        client = get_stripe_client()
        
        subscription = client.Subscription.retrieve(
            stripe_subscription_id,
            expand=['customer', 'latest_invoice', 'default_payment_method']
        )
        
        customer = subscription.customer if hasattr(subscription, 'customer') else None
        latest_invoice = subscription.latest_invoice if hasattr(subscription, 'latest_invoice') else None
        
        billing_info = {
            'subscription_id': subscription.id,
            'status': subscription.status,
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start).isoformat() if subscription.current_period_start else None,
            'current_period_end': datetime.fromtimestamp(subscription.current_period_end).isoformat() if subscription.current_period_end else None,
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'canceled_at': datetime.fromtimestamp(subscription.canceled_at).isoformat() if subscription.canceled_at else None,
            'created': datetime.fromtimestamp(subscription.created).isoformat() if subscription.created else None,
            'billing_interval': None,
            'billing_interval_count': None,
            'amount': None,
            'currency': None,
        }
        
        if subscription.items and subscription.items.data:
            price = subscription.items.data[0].price
            if price:
                billing_info['amount'] = price.unit_amount / 100 if price.unit_amount else None
                billing_info['currency'] = price.currency.upper() if price.currency else None
                if price.recurring:
                    billing_info['billing_interval'] = price.recurring.interval
                    billing_info['billing_interval_count'] = price.recurring.interval_count
        
        if customer and hasattr(customer, 'id'):
            billing_info['customer'] = {
                'id': customer.id,
                'email': customer.email if hasattr(customer, 'email') else None,
                'name': customer.name if hasattr(customer, 'name') else None,
                'created': datetime.fromtimestamp(customer.created).isoformat() if hasattr(customer, 'created') and customer.created else None,
            }
        
        if latest_invoice and hasattr(latest_invoice, 'id'):
            billing_info['latest_invoice'] = {
                'id': latest_invoice.id,
                'status': latest_invoice.status if hasattr(latest_invoice, 'status') else None,
                'amount_paid': latest_invoice.amount_paid / 100 if hasattr(latest_invoice, 'amount_paid') and latest_invoice.amount_paid else None,
                'amount_due': latest_invoice.amount_due / 100 if hasattr(latest_invoice, 'amount_due') and latest_invoice.amount_due else None,
                'currency': latest_invoice.currency.upper() if hasattr(latest_invoice, 'currency') and latest_invoice.currency else None,
                'created': datetime.fromtimestamp(latest_invoice.created).isoformat() if hasattr(latest_invoice, 'created') and latest_invoice.created else None,
                'paid_at': datetime.fromtimestamp(latest_invoice.status_transitions.paid_at).isoformat() if hasattr(latest_invoice, 'status_transitions') and latest_invoice.status_transitions and latest_invoice.status_transitions.paid_at else None,
            }
        
        try:
            upcoming = client.Invoice.upcoming(subscription=stripe_subscription_id)
            if upcoming:
                billing_info['upcoming_invoice'] = {
                    'amount_due': upcoming.amount_due / 100 if upcoming.amount_due else None,
                    'currency': upcoming.currency.upper() if upcoming.currency else None,
                    'next_payment_attempt': datetime.fromtimestamp(upcoming.next_payment_attempt).isoformat() if upcoming.next_payment_attempt else None,
                }
        except stripe.error.InvalidRequestError:
            billing_info['upcoming_invoice'] = None
        
        return billing_info
        
    except stripe.error.InvalidRequestError as e:
        print(f"[Stripe] Invalid request for subscription {stripe_subscription_id}: {e}")
        return None
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return None
    except Exception as e:
        print(f"[Stripe] Error fetching subscription {stripe_subscription_id}: {e}")
        return None

def get_customer_billing_info(stripe_customer_id):
    """
    Fetch billing information for a customer from Stripe
    Returns dict with customer billing details or None if not found
    """
    if not stripe_customer_id:
        return None
    
    try:
        client = get_stripe_client()
        
        customer = client.Customer.retrieve(
            stripe_customer_id,
            expand=['subscriptions', 'invoice_settings.default_payment_method']
        )
        
        customer_info = {
            'customer_id': customer.id,
            'email': customer.email,
            'name': customer.name,
            'created': datetime.fromtimestamp(customer.created).isoformat() if customer.created else None,
            'balance': customer.balance / 100 if customer.balance else 0,
            'currency': customer.currency.upper() if customer.currency else 'USD',
            'delinquent': customer.delinquent if hasattr(customer, 'delinquent') else False,
        }
        
        if customer.subscriptions and customer.subscriptions.data:
            customer_info['subscriptions'] = []
            for sub in customer.subscriptions.data:
                sub_info = {
                    'id': sub.id,
                    'status': sub.status,
                    'current_period_start': datetime.fromtimestamp(sub.current_period_start).isoformat() if sub.current_period_start else None,
                    'current_period_end': datetime.fromtimestamp(sub.current_period_end).isoformat() if sub.current_period_end else None,
                }
                customer_info['subscriptions'].append(sub_info)
        
        invoices = client.Invoice.list(customer=stripe_customer_id, limit=5)
        if invoices and invoices.data:
            customer_info['recent_invoices'] = []
            for inv in invoices.data:
                inv_info = {
                    'id': inv.id,
                    'status': inv.status,
                    'amount_paid': inv.amount_paid / 100 if inv.amount_paid else 0,
                    'amount_due': inv.amount_due / 100 if inv.amount_due else 0,
                    'currency': inv.currency.upper() if inv.currency else 'USD',
                    'created': datetime.fromtimestamp(inv.created).isoformat() if inv.created else None,
                }
                customer_info['recent_invoices'].append(inv_info)
        
        return customer_info
        
    except stripe.error.InvalidRequestError as e:
        print(f"[Stripe] Invalid request for customer {stripe_customer_id}: {e}")
        return None
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return None
    except Exception as e:
        print(f"[Stripe] Error fetching customer {stripe_customer_id}: {e}")
        return None

def get_revenue_metrics(subscription_ids):
    """
    Fetch revenue metrics from Stripe for given subscription IDs
    
    Returns:
        dict with:
        - total_revenue: Total amount actually collected (amount_paid after discounts)
        - monthly_rebill: Expected renewals at FULL plan price (before discounts)
        - subscription_count: Number of active subscriptions
    """
    if not subscription_ids:
        return {
            'total_revenue': 0,
            'monthly_rebill': 0,
            'subscription_count': 0,
            'currency': 'USD'
        }
    
    try:
        client = get_stripe_client()
        
        total_revenue = 0
        monthly_rebill = 0
        active_count = 0
        
        # Get current month boundaries
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            month_end = datetime(now.year + 1, 1, 1)
        else:
            month_end = datetime(now.year, now.month + 1, 1)
        
        for sub_id in subscription_ids:
            if not sub_id:
                continue
                
            try:
                # Get subscription details
                subscription = client.Subscription.retrieve(sub_id)
                
                if subscription.status in ['active', 'trialing']:
                    active_count += 1
                
                # Get the plan's base price (unit_amount before any discounts)
                plan_price = 0
                if subscription.items and subscription.items.data:
                    price = subscription.items.data[0].price
                    if price and price.unit_amount:
                        plan_price = price.unit_amount / 100
                
                # Get all paid invoices for this subscription
                # amount_paid = actual cash collected AFTER discounts
                invoices = client.Invoice.list(
                    subscription=sub_id,
                    status='paid',
                    limit=100
                )
                
                for invoice in invoices.auto_paging_iter():
                    # amount_paid is the actual amount collected (after discounts)
                    amount_paid = (invoice.amount_paid or 0) / 100
                    total_revenue += amount_paid
                    print(f"[Stripe] Invoice {invoice.id}: amount_paid=${amount_paid}")
                
                # Check if subscription renews this month - use FULL plan price
                if subscription.status == 'active' and not subscription.cancel_at_period_end:
                    if subscription.current_period_end:
                        next_billing = datetime.fromtimestamp(subscription.current_period_end)
                        if month_start <= next_billing < month_end:
                            # Use full plan price, not discounted amount
                            monthly_rebill += plan_price
                            print(f"[Stripe] Sub {sub_id} renews {next_billing.date()} at full price ${plan_price}")
                    
            except stripe.error.InvalidRequestError as e:
                print(f"[Stripe] Subscription {sub_id} not found: {e}")
                continue
            except Exception as e:
                print(f"[Stripe] Error fetching subscription {sub_id}: {e}")
                continue
        
        print(f"[Stripe] Revenue metrics: total_revenue=${total_revenue}, monthly_rebill=${monthly_rebill}")
        
        return {
            'total_revenue': round(total_revenue, 2),
            'monthly_rebill': round(monthly_rebill, 2),
            'subscription_count': active_count,
            'currency': 'USD'
        }
        
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return None
    except Exception as e:
        print(f"[Stripe] Error fetching revenue metrics: {e}")
        return None


def cancel_subscription(stripe_subscription_id, cancel_immediately=False):
    """
    Cancel a Stripe subscription
    
    Args:
        stripe_subscription_id: The Stripe subscription ID to cancel
        cancel_immediately: If True, cancels immediately. If False, cancels at period end.
    
    Returns:
        dict with cancellation result or error
    """
    if not stripe_subscription_id:
        return {'success': False, 'error': 'No subscription ID provided'}
    
    try:
        client = get_stripe_client()
        
        if cancel_immediately:
            # Cancel immediately - subscription ends now
            subscription = client.Subscription.cancel(stripe_subscription_id)
            return {
                'success': True,
                'subscription_id': subscription.id,
                'status': subscription.status,
                'canceled_at': datetime.fromtimestamp(subscription.canceled_at).isoformat() if subscription.canceled_at else None,
                'message': 'Subscription canceled immediately'
            }
        else:
            # Cancel at period end - subscription remains active until current period ends
            subscription = client.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True
            )
            return {
                'success': True,
                'subscription_id': subscription.id,
                'status': subscription.status,
                'cancel_at_period_end': subscription.cancel_at_period_end,
                'current_period_end': datetime.fromtimestamp(subscription.current_period_end).isoformat() if subscription.current_period_end else None,
                'message': 'Subscription will cancel at end of billing period'
            }
        
    except stripe.error.InvalidRequestError as e:
        print(f"[Stripe] Invalid request to cancel subscription {stripe_subscription_id}: {e}")
        return {'success': False, 'error': str(e)}
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return {'success': False, 'error': 'Stripe authentication failed'}
    except Exception as e:
        print(f"[Stripe] Error canceling subscription {stripe_subscription_id}: {e}")
        return {'success': False, 'error': str(e)}
