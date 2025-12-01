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
    """Fetch Stripe credentials from Replit connection API"""
    global _stripe_credentials
    
    if _stripe_credentials:
        return _stripe_credentials
    
    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    
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
    
    if not settings.get('publishable') or not settings.get('secret'):
        raise Exception(f'Stripe {target_environment} connection not found')
    
    _stripe_credentials = {
        'publishable_key': settings['publishable'],
        'secret_key': settings['secret']
    }
    
    return _stripe_credentials

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
