"""
Stripe Client for Python
Fetches credentials from Replit connection API and provides Stripe access
"""
import os
import stripe
import requests
from datetime import datetime, timedelta

_stripe_credentials = None

def get_stripe_credentials():
    """
    Fetch Stripe credentials - prioritizes manual env vars (live keys), then Replit connector
    
    Supports:
    1. Manual env vars: STRIPE_SECRET_KEY/STRIPE_SECRET (preferred - allows using live keys in dev)
    2. Replit Stripe Connector (fallback)
    """
    global _stripe_credentials
    
    if _stripe_credentials:
        return _stripe_credentials
    
    # First, check for manual environment variables (preferred - allows live keys in dev)
    manual_secret = os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET')
    manual_publishable = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    
    if manual_secret:
        # Detect if it's a live or test key
        key_type = 'LIVE' if 'live' in manual_secret else 'TEST'
        print(f"[STRIPE] Using manual environment variables ({key_type} mode)")
        _stripe_credentials = {
            'publishable_key': manual_publishable or '',
            'secret_key': manual_secret
        }
        return _stripe_credentials
    
    # Fall back to Replit connector API
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
            print(f"[STRIPE] Replit connector failed: {e}")
    
    # Neither worked
    raise Exception('Stripe credentials not found. Set STRIPE_SECRET_KEY environment variable or set up Replit Stripe connector.')

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
        
        # Use safe dict access for all fields
        customer = subscription.get('customer')
        latest_invoice = subscription.get('latest_invoice')
        
        # Get period fields safely (may not exist in newer billing modes)
        current_period_start = subscription.get('current_period_start')
        current_period_end = subscription.get('current_period_end')
        canceled_at = subscription.get('canceled_at')
        created = subscription.get('created')
        
        billing_info = {
            'subscription_id': subscription.get('id'),
            'status': subscription.get('status'),
            'current_period_start': datetime.fromtimestamp(current_period_start).isoformat() if current_period_start else None,
            'current_period_end': datetime.fromtimestamp(current_period_end).isoformat() if current_period_end else None,
            'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
            'canceled_at': datetime.fromtimestamp(canceled_at).isoformat() if canceled_at else None,
            'created': datetime.fromtimestamp(created).isoformat() if created else None,
            'billing_interval': None,
            'billing_interval_count': None,
            'amount': None,
            'currency': None,
        }
        
        # Get items safely
        items_data = subscription.get('items', {})
        if items_data and hasattr(items_data, 'data') and items_data.data:
            item = items_data.data[0]
            price = item.get('price') if isinstance(item, dict) else getattr(item, 'price', None)
            if price:
                unit_amount = price.get('unit_amount') if isinstance(price, dict) else getattr(price, 'unit_amount', None)
                currency = price.get('currency') if isinstance(price, dict) else getattr(price, 'currency', None)
                recurring = price.get('recurring') if isinstance(price, dict) else getattr(price, 'recurring', None)
                
                billing_info['amount'] = unit_amount / 100 if unit_amount else None
                billing_info['currency'] = currency.upper() if currency else None
                if recurring:
                    billing_info['billing_interval'] = recurring.get('interval') if isinstance(recurring, dict) else getattr(recurring, 'interval', None)
                    billing_info['billing_interval_count'] = recurring.get('interval_count') if isinstance(recurring, dict) else getattr(recurring, 'interval_count', None)
        
        if customer:
            cust_id = customer.get('id') if isinstance(customer, dict) else getattr(customer, 'id', None)
            if cust_id:
                billing_info['customer'] = {
                    'id': cust_id,
                    'email': customer.get('email') if isinstance(customer, dict) else getattr(customer, 'email', None),
                    'name': customer.get('name') if isinstance(customer, dict) else getattr(customer, 'name', None),
                    'created': datetime.fromtimestamp(customer.get('created') if isinstance(customer, dict) else getattr(customer, 'created', None)).isoformat() if (customer.get('created') if isinstance(customer, dict) else getattr(customer, 'created', None)) else None,
                }
        
        if latest_invoice:
            inv_id = latest_invoice.get('id') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'id', None)
            if inv_id:
                inv_amount_paid = latest_invoice.get('amount_paid') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'amount_paid', None)
                inv_amount_due = latest_invoice.get('amount_due') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'amount_due', None)
                inv_currency = latest_invoice.get('currency') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'currency', None)
                inv_created = latest_invoice.get('created') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'created', None)
                inv_status = latest_invoice.get('status') if isinstance(latest_invoice, dict) else getattr(latest_invoice, 'status', None)
                
                billing_info['latest_invoice'] = {
                    'id': inv_id,
                    'status': inv_status,
                    'amount_paid': inv_amount_paid / 100 if inv_amount_paid else None,
                    'amount_due': inv_amount_due / 100 if inv_amount_due else None,
                    'currency': inv_currency.upper() if inv_currency else None,
                    'created': datetime.fromtimestamp(inv_created).isoformat() if inv_created else None,
                    'paid_at': None,
                }
        
        # Get upcoming invoice using create_preview (Stripe API v5+)
        try:
            upcoming = stripe.Invoice.create_preview(subscription=stripe_subscription_id)
            if upcoming:
                next_payment = upcoming.get('next_payment_attempt') or upcoming.get('period_end')
                billing_info['upcoming_invoice'] = {
                    'amount_due': upcoming.get('amount_due', 0) / 100 if upcoming.get('amount_due') else None,
                    'currency': upcoming.get('currency', '').upper() if upcoming.get('currency') else None,
                    'next_payment_attempt': datetime.fromtimestamp(next_payment).isoformat() if next_payment else None,
                }
        except Exception:
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

# Revenue metrics cache with TTL
_metrics_cache = {
    'data': None,
    'expires_at': None
}
METRICS_CACHE_TTL_SECONDS = 30  # 30 seconds cache for fresh data

def get_stripe_metrics(subscription_ids=None, product_name_filter="VIP"):
    """
    Fetch revenue metrics directly from Stripe API.
    
    Simple approach:
    1. Get ALL paid invoices from Stripe
    2. Filter by line item description containing "VIP"
    3. Sum the amounts paid (respects discounts)
    
    Returns:
        dict with total_revenue, monthly_rebill, subscription_count, currency
    """
    # Check cache first
    now = datetime.now()
    if (_metrics_cache['data'] and 
        _metrics_cache['expires_at'] and 
        _metrics_cache['expires_at'] > now):
        print(f"[Stripe] Returning cached metrics")
        return _metrics_cache['data']
    
    print(f"[Stripe] Fetching revenue metrics from Stripe (filter: '{product_name_filter}')...")
    
    try:
        client = get_stripe_client()
        
        total_revenue = 0
        active_sub_ids = set()
        invoice_count = 0
        
        # ========== REVENUE: Get ALL paid invoices ==========
        print(f"[Stripe] Fetching all paid invoices...")
        for invoice in client.Invoice.list(status='paid', limit=100, expand=['data.lines.data', 'data.subscription']).auto_paging_iter():
            # Check each line item for VIP products
            if invoice.lines and invoice.lines.data:
                for line in invoice.lines.data:
                    description = line.description or ''
                    # Check if this invoice is for a VIP product
                    if product_name_filter.lower() in description.lower():
                        amount = (invoice.amount_paid or 0) / 100
                        total_revenue += amount
                        invoice_count += 1
                        # Get subscription ID - safely handle missing attribute
                        sub_id = None
                        if hasattr(invoice, 'subscription') and invoice.subscription:
                            sub = invoice.subscription
                            # If expanded, it's an object with .id; otherwise it's a string
                            sub_id = sub.id if hasattr(sub, 'id') else str(sub)
                        
                        if sub_id:
                            active_sub_ids.add(sub_id)
                            print(f"[Stripe] Invoice: ${amount} - {description[:40]} (sub: {sub_id[:15]}...)")
                        else:
                            print(f"[Stripe] Invoice: ${amount} - {description[:40]} (no sub)")
                        break  # Count each invoice once
        
        print(f"[Stripe] Total revenue from {invoice_count} VIP invoices: ${total_revenue}")
        print(f"[Stripe] Found {len(active_sub_ids)} subscription IDs from invoices")
        
        # ========== ALSO FETCH ACTIVE SUBSCRIPTIONS DIRECTLY ==========
        # Some invoices don't have subscription IDs, so also check active subscriptions
        print(f"[Stripe] Also fetching active subscriptions directly from Stripe...")
        for sub in client.Subscription.list(status='active', limit=100).auto_paging_iter():
            # Check if this subscription is for a VIP product
            # Access items via subscription['items'] to avoid method call issue
            items_data = sub.get('items', {})
            if items_data and hasattr(items_data, 'data'):
                for item in items_data.data:
                    product_name = ''
                    # Get product name - fetch product if needed
                    price = item.get('price', {}) if isinstance(item, dict) else getattr(item, 'price', None)
                    if price:
                        product_id = price.get('product') if isinstance(price, dict) else getattr(price, 'product', None)
                        if product_id:
                            if isinstance(product_id, str):
                                # Product is just an ID, fetch it
                                try:
                                    prod_obj = client.Product.retrieve(product_id)
                                    product_name = prod_obj.name or ''
                                except:
                                    product_name = price.get('nickname', '') if isinstance(price, dict) else getattr(price, 'nickname', '') or ''
                            elif hasattr(product_id, 'name'):
                                product_name = product_id.name
                    
                    if product_name and product_name_filter.lower() in product_name.lower():
                        active_sub_ids.add(sub.id)
                        print(f"[Stripe] Found active VIP sub: {sub.id[:15]}... - {product_name}")
                        break
        
        print(f"[Stripe] Total subscription IDs to check: {len(active_sub_ids)}")
        
        # ========== REBILL: Check active subscriptions ==========
        monthly_rebill = 0
        active_count = 0
        month_start = datetime(now.year, now.month, 1)
        month_end = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        
        print(f"[Stripe] Checking {len(active_sub_ids)} subscriptions for rebill (month: {month_start.date()} to {month_end.date()})...")
        
        # Check subscriptions we found from invoices
        for sub_id in active_sub_ids:
            try:
                sub = client.Subscription.retrieve(sub_id)
                
                # Use attribute access for Stripe objects (not dict .get())
                status = getattr(sub, 'status', 'unknown')
                cancel_at_period_end = getattr(sub, 'cancel_at_period_end', False)
                customer_id = getattr(sub, 'customer', None)
                
                print(f"[Stripe] Sub {sub_id[:15]}... status={status}, cancel_at_end={cancel_at_period_end}")
                
                if status == 'active':
                    active_count += 1
                    
                    # Skip if set to cancel at period end
                    if cancel_at_period_end:
                        print(f"[Stripe] Sub will cancel at period end, skipping rebill")
                        continue
                    
                    # Try to get upcoming invoice - simplest approach
                    # If no upcoming invoice exists (one-time/lifetime), Stripe returns error
                    try:
                        # Use stripe module directly - StripeClient uses different path
                        upcoming = stripe.Invoice.upcoming(subscription=sub_id)
                        
                        # Get the next payment date - try multiple fields
                        next_payment_ts = getattr(upcoming, 'next_payment_attempt', None)
                        if not next_payment_ts:
                            next_payment_ts = getattr(upcoming, 'due_date', None)
                        if not next_payment_ts:
                            next_payment_ts = getattr(upcoming, 'period_end', None)
                        
                        # total already includes discounts/coupons
                        rebill_amount = (getattr(upcoming, 'total', 0) or 0) / 100
                        
                        print(f"[Stripe] Upcoming invoice: ${rebill_amount}, next_payment_ts={next_payment_ts}")
                        
                        if next_payment_ts:
                            next_payment_date = datetime.fromtimestamp(next_payment_ts)
                            
                            # Check if renews this month
                            if month_start <= next_payment_date < month_end:
                                monthly_rebill += rebill_amount
                                print(f"[Stripe] ✓ Rebill this month: ${rebill_amount} on {next_payment_date.date()}")
                            else:
                                print(f"[Stripe] Sub renews {next_payment_date.date()} (not this month)")
                        else:
                            # No date but has upcoming invoice - count it as this month
                            monthly_rebill += rebill_amount
                            print(f"[Stripe] ✓ Rebill (date unknown): ${rebill_amount}")
                            
                    except stripe.error.InvalidRequestError as e:
                        # No upcoming invoice - likely one-time/lifetime subscription
                        print(f"[Stripe] No upcoming invoice: {str(e)[:50]}...")
                    except Exception as e:
                        print(f"[Stripe] Upcoming invoice error: {e}")
            except Exception as e:
                print(f"[Stripe] Sub check error for {sub_id}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"[Stripe] Active: {active_count}, Rebill this month: ${monthly_rebill}")
        
        result = {
            'total_revenue': round(total_revenue, 2),
            'monthly_rebill': round(monthly_rebill, 2),
            'subscription_count': active_count,
            'currency': 'USD'
        }
        
        # Update cache
        _metrics_cache['data'] = result
        _metrics_cache['expires_at'] = now + timedelta(seconds=METRICS_CACHE_TTL_SECONDS)
        
        return result
        
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return None
    except Exception as e:
        print(f"[Stripe] Error fetching metrics: {e}")
        import traceback
        traceback.print_exc()
        return None


# Legacy function - kept for backward compatibility
_revenue_cache = {
    'data': None,
    'expires_at': None,
    'subscription_ids_hash': None
}
REVENUE_CACHE_TTL_SECONDS = 300  # 5 minutes

def get_revenue_metrics(subscription_ids):
    """
    Fetch revenue metrics from Stripe for given subscription IDs.
    
    Optimized with:
    - 5-minute caching to reduce API calls
    - Batch invoice retrieval
    - Rate-limit aware design
    
    Returns:
        dict with:
        - total_revenue: Total amount actually collected (amount_paid after discounts)
        - monthly_rebill: Expected renewals this month
        - subscription_count: Number of active subscriptions
    """
    if not subscription_ids:
        return {
            'total_revenue': 0,
            'monthly_rebill': 0,
            'subscription_count': 0,
            'currency': 'USD'
        }
    
    # Create hash of subscription IDs for cache invalidation
    sub_ids_sorted = sorted([s for s in subscription_ids if s])
    sub_ids_hash = hash(tuple(sub_ids_sorted))
    
    # Check cache
    now = datetime.now()
    if (_revenue_cache['data'] and 
        _revenue_cache['expires_at'] and 
        _revenue_cache['expires_at'] > now and
        _revenue_cache['subscription_ids_hash'] == sub_ids_hash):
        print(f"[Stripe] Returning cached revenue metrics (expires in {(_revenue_cache['expires_at'] - now).seconds}s)")
        return _revenue_cache['data']
    
    try:
        client = get_stripe_client()
        
        total_revenue = 0
        monthly_rebill = 0
        active_count = 0
        
        # Get current month boundaries
        month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            month_end = datetime(now.year + 1, 1, 1)
        else:
            month_end = datetime(now.year, now.month + 1, 1)
        
        # Fetch paid invoices for all matching subscriptions
        print(f"[Stripe] Fetching revenue metrics for {len(sub_ids_sorted)} subscriptions")
        
        # Get all paid invoices (not filtered by date - sum ALL revenue ever collected)
        all_invoices = client.Invoice.list(status='paid', limit=100)
        
        for invoice in all_invoices.auto_paging_iter():
            sub_id = invoice.subscription
            if sub_id and sub_id in sub_ids_sorted:
                # Use amount_paid which respects discounts/coupons
                amount_paid = (invoice.amount_paid or 0) / 100
                total_revenue += amount_paid
                print(f"[Stripe] Invoice {invoice.id}: sub={sub_id}, amount_paid=${amount_paid}")
        
        print(f"[Stripe] Total revenue from paid invoices: ${total_revenue}")
        
        # Process subscriptions for active count and rebill
        print(f"[Stripe] Month boundaries: {month_start.date()} to {month_end.date()}")
        for sub_id in sub_ids_sorted:
            try:
                subscription = client.Subscription.retrieve(sub_id)
                
                if subscription.status in ['active', 'trialing']:
                    active_count += 1
                
                # Check if subscription will renew this month (use current_period_end, NOT next_payment_attempt)
                if subscription.status == 'active' and not subscription.cancel_at_period_end:
                    period_end = datetime.fromtimestamp(subscription.current_period_end) if subscription.current_period_end else None
                    
                    if period_end and month_start <= period_end < month_end:
                        # Renewal is this month - get the upcoming invoice amount
                        try:
                            upcoming = stripe.Invoice.upcoming(subscription=sub_id)
                            if upcoming:
                                # Use amount_due (or total as fallback)
                                upcoming_amount = (upcoming.amount_due or upcoming.total or 0) / 100
                                monthly_rebill += upcoming_amount
                                print(f"[Stripe] Sub {sub_id} renews {period_end.date()} for ${upcoming_amount}")
                        except stripe.error.InvalidRequestError:
                            # No upcoming invoice - use subscription plan price as fallback
                            if subscription.items and subscription.items.data:
                                plan_amount = (subscription.items.data[0].price.unit_amount or 0) / 100
                                monthly_rebill += plan_amount
                                print(f"[Stripe] Sub {sub_id} renews {period_end.date()} for ~${plan_amount} (plan price)")
                        except Exception as e:
                            print(f"[Stripe] Error getting upcoming invoice for {sub_id}: {e}")
                    else:
                        print(f"[Stripe] Sub {sub_id} renews {period_end.date() if period_end else 'N/A'} (not this month)")
                        
            except stripe.error.InvalidRequestError as e:
                print(f"[Stripe] Subscription {sub_id} not found: {e}")
            except Exception as e:
                print(f"[Stripe] Error fetching subscription {sub_id}: {e}")
        
        result = {
            'total_revenue': round(total_revenue, 2),
            'monthly_rebill': round(monthly_rebill, 2),
            'subscription_count': active_count,
            'currency': 'USD'
        }
        
        # Update cache
        _revenue_cache['data'] = result
        _revenue_cache['expires_at'] = now + timedelta(seconds=REVENUE_CACHE_TTL_SECONDS)
        _revenue_cache['subscription_ids_hash'] = sub_ids_hash
        
        print(f"[Stripe] Revenue metrics cached: total_revenue=${total_revenue}, monthly_rebill=${monthly_rebill}")
        
        return result
        
    except stripe.error.AuthenticationError as e:
        print(f"[Stripe] Authentication error: {e}")
        return None
    except Exception as e:
        print(f"[Stripe] Error fetching revenue metrics: {e}")
        return None


def get_rebill_this_month(subscription_ids):
    """
    Calculate total rebill amount for subscriptions renewing this month.
    
    Uses subscription.current_period_end to determine if renewal is this month,
    then fetches upcoming invoice amount.
    
    Args:
        subscription_ids: List of Stripe subscription IDs
        
    Returns:
        float: Total rebill amount for this month
    """
    if not subscription_ids:
        return 0
    
    try:
        client = get_stripe_client()
        now = datetime.now()
        
        # Get current month boundaries
        month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            month_end = datetime(now.year + 1, 1, 1)
        else:
            month_end = datetime(now.year, now.month + 1, 1)
        
        monthly_rebill = 0
        
        print(f"[Stripe] Calculating rebill for {len(subscription_ids)} subscriptions")
        print(f"[Stripe] Month window: {month_start.date()} to {month_end.date()}")
        
        for sub_id in subscription_ids:
            try:
                subscription = client.Subscription.retrieve(sub_id)
                
                # Skip if not active or canceling
                if subscription.status != 'active' or subscription.cancel_at_period_end:
                    print(f"[Stripe] Sub {sub_id}: skipped (status={subscription.status}, cancel_at_end={subscription.cancel_at_period_end})")
                    continue
                
                # Check if current_period_end is this month
                period_end = datetime.fromtimestamp(subscription.current_period_end) if subscription.current_period_end else None
                
                if period_end and month_start <= period_end < month_end:
                    # Renewal is this month - get upcoming invoice amount
                    try:
                        upcoming = stripe.Invoice.upcoming(subscription=sub_id)
                        if upcoming:
                            amount = (upcoming.amount_due or upcoming.total or 0) / 100
                            monthly_rebill += amount
                            print(f"[Stripe] Sub {sub_id}: renews {period_end.date()} for ${amount}")
                    except stripe.error.InvalidRequestError:
                        # No upcoming invoice - use plan price
                        if subscription.items and subscription.items.data:
                            amount = (subscription.items.data[0].price.unit_amount or 0) / 100
                            monthly_rebill += amount
                            print(f"[Stripe] Sub {sub_id}: renews {period_end.date()} for ~${amount} (plan)")
                else:
                    print(f"[Stripe] Sub {sub_id}: renews {period_end.date() if period_end else 'N/A'} (not this month)")
                    
            except stripe.error.InvalidRequestError as e:
                print(f"[Stripe] Subscription {sub_id} not found: {e}")
            except Exception as e:
                print(f"[Stripe] Error processing {sub_id}: {e}")
        
        print(f"[Stripe] Total rebill this month: ${monthly_rebill}")
        return round(monthly_rebill, 2)
        
    except Exception as e:
        print(f"[Stripe] Error calculating rebill: {e}")
        return 0


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


def verify_webhook_signature(payload, sig_header, webhook_secret):
    """
    Verify Stripe webhook signature
    
    Args:
        payload: Raw request body bytes
        sig_header: Stripe-Signature header value
        webhook_secret: Webhook signing secret from Stripe
    
    Returns:
        tuple: (event_dict or None, error_message or None)
    """
    try:
        client = get_stripe_client()
        event = client.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event, None
    except ValueError as e:
        print(f"[Stripe Webhook] Invalid payload: {e}")
        return None, "Invalid payload"
    except stripe.error.SignatureVerificationError as e:
        print(f"[Stripe Webhook] Invalid signature: {e}")
        return None, "Invalid signature"
    except Exception as e:
        print(f"[Stripe Webhook] Error verifying webhook: {e}")
        return None, str(e)


def get_subscription_details(subscription_id):
    """
    Fetch subscription details from Stripe
    
    Returns dict with subscription info or None
    """
    try:
        client = get_stripe_client()
        subscription = client.Subscription.retrieve(
            subscription_id,
            expand=['customer', 'latest_invoice']
        )
        
        # Get customer email
        customer = subscription.customer
        email = customer.email if hasattr(customer, 'email') else None
        name = customer.name if hasattr(customer, 'name') else None
        
        # Get amount from latest invoice
        amount_paid = 0
        if subscription.latest_invoice and hasattr(subscription.latest_invoice, 'amount_paid'):
            amount_paid = subscription.latest_invoice.amount_paid / 100
        
        # Get plan info
        plan_name = None
        if subscription.items and subscription.items.data:
            item = subscription.items.data[0]
            if item.price and item.price.product:
                # Product might be an ID or expanded object
                product = item.price.product
                if hasattr(product, 'name'):
                    plan_name = product.name
        
        return {
            'subscription_id': subscription.id,
            'customer_id': customer.id if hasattr(customer, 'id') else subscription.customer,
            'email': email,
            'name': name,
            'status': subscription.status,
            'plan_name': plan_name,
            'amount_paid': amount_paid,
            'current_period_start': subscription.current_period_start,
            'current_period_end': subscription.current_period_end,
            'cancel_at_period_end': subscription.cancel_at_period_end
        }
    except Exception as e:
        print(f"[Stripe] Error fetching subscription {subscription_id}: {e}")
        return None


def fetch_active_subscriptions():
    """
    Fetch all active subscriptions from Stripe for backfill purposes.
    
    Gets total amount paid from ALL invoices for each subscription,
    not just the latest invoice (which might be a renewal or different amount).
    
    Returns list of subscription dicts
    """
    try:
        client = get_stripe_client()
        subscriptions = []
        
        print(f"[Stripe] Fetching active subscriptions for sync...")
        
        # Fetch active subscriptions
        for sub in client.Subscription.list(status='active', expand=['data.customer']).auto_paging_iter():
            customer = sub.customer
            email = customer.email if hasattr(customer, 'email') else None
            name = customer.name if hasattr(customer, 'name') else None
            
            # Get total amount paid from ALL invoices for this subscription
            total_paid = 0
            try:
                invoices = client.Invoice.list(subscription=sub.id, status='paid', limit=100)
                for invoice in invoices.auto_paging_iter():
                    total_paid += (invoice.amount_paid or 0) / 100
                print(f"[Stripe] Sub {sub.id[:20]}...: {email}, total_paid=${total_paid}")
            except Exception as e:
                print(f"[Stripe] Error fetching invoices for {sub.id}: {e}")
            
            plan_name = None
            if sub.items and sub.items.data:
                item = sub.items.data[0]
                if item.price and item.price.product:
                    product = item.price.product
                    if hasattr(product, 'name'):
                        plan_name = product.name
            
            subscriptions.append({
                'subscription_id': sub.id,
                'customer_id': customer.id if hasattr(customer, 'id') else sub.customer,
                'email': email,
                'name': name,
                'status': sub.status,
                'plan_name': plan_name,
                'amount_paid': round(total_paid, 2)
            })
        
        print(f"[Stripe] Found {len(subscriptions)} active subscriptions")
        return subscriptions
    except Exception as e:
        print(f"[Stripe] Error fetching active subscriptions: {e}")
        import traceback
        traceback.print_exc()
        return []
