"""
Stripe webhook HTTP handler.

Extracted from server.py - handles incoming Stripe webhook POST requests.
Handler receives dependencies as parameters to avoid stale module globals.

Tenant-aware: Resolves tenant from price_id and only grants VIP access
if the subscription's price matches the tenant's configured vip_price_id.
"""
import json
import os


def get_subscription_price_id(subscription_data):
    """
    Extract the price_id from subscription data.
    Looks in items.data[0].price.id or plan.id.
    
    Args:
        subscription_data: Subscription object from Stripe (dict or object)
        
    Returns:
        price_id string or None
    """
    try:
        if isinstance(subscription_data, dict):
            items = subscription_data.get('items', {})
            if isinstance(items, dict):
                data = items.get('data', [])
            else:
                data = getattr(items, 'data', [])
            
            if data and len(data) > 0:
                item = data[0]
                if isinstance(item, dict):
                    price = item.get('price', {})
                    if isinstance(price, dict):
                        return price.get('id')
                    return getattr(price, 'id', None)
                else:
                    price = getattr(item, 'price', None)
                    if price:
                        return getattr(price, 'id', None)
            
            plan = subscription_data.get('plan')
            if plan:
                if isinstance(plan, dict):
                    return plan.get('id')
                return getattr(plan, 'id', None)
        else:
            items = getattr(subscription_data, 'items', None)
            if items:
                data = getattr(items, 'data', [])
                if data and len(data) > 0:
                    price = getattr(data[0], 'price', None)
                    if price:
                        return getattr(price, 'id', None)
            
            plan = getattr(subscription_data, 'plan', None)
            if plan:
                return getattr(plan, 'id', None)
    except Exception as e:
        print(f"[STRIPE WEBHOOK] Error extracting price_id: {e}")
    
    return None


def resolve_tenant_and_vip_status(db_module, price_id, subscription_id=None):
    """
    Resolve tenant from price_id and determine if it's a VIP subscription.
    
    Args:
        db_module: Database module
        price_id: Stripe price ID from subscription
        subscription_id: Optional subscription ID to look up existing tenant
        
    Returns:
        Tuple of (tenant_id, vip_price_id, is_vip) 
        - tenant_id: The tenant this price belongs to, or 'entrylab' as fallback
        - vip_price_id: The tenant's configured VIP price ID
        - is_vip: True if price_id matches vip_price_id
    """
    if not price_id:
        if subscription_id:
            tenant_id = db_module.get_tenant_id_by_subscription_id(subscription_id)
            if tenant_id:
                settings = db_module.get_tenant_stripe_settings(tenant_id)
                vip_price_id = settings.get('vip_price_id') if settings else None
                return tenant_id, vip_price_id, False
        return 'entrylab', None, False
    
    tenant_id, vip_price_id = db_module.resolve_tenant_from_price_id(price_id)
    
    if tenant_id:
        is_vip = price_id == vip_price_id if vip_price_id else False
        return tenant_id, vip_price_id, is_vip
    
    entrylab_vip_price = os.environ.get('ENTRYLAB_VIP_PRICE_ID')
    if entrylab_vip_price and price_id == entrylab_vip_price:
        return 'entrylab', entrylab_vip_price, True
    
    entrylab_settings = db_module.get_tenant_stripe_settings('entrylab')
    if entrylab_settings:
        entrylab_vip = entrylab_settings.get('vip_price_id')
        if entrylab_vip and price_id == entrylab_vip:
            return 'entrylab', entrylab_vip, True
    
    print(f"[STRIPE WEBHOOK] ⚠️ Price not found in any tenant's cache, skipping VIP grant")
    return (None, None, False)


def handle_stripe_webhook(handler, stripe_available, telegram_bot_available, db_module):
    """POST /api/stripe/webhook - Stripe webhook handler
    
    Args:
        handler: HTTP request handler
        stripe_available: STRIPE_AVAILABLE flag
        telegram_bot_available: TELEGRAM_BOT_AVAILABLE flag
        db_module: Database module for idempotency and subscription updates
    """
    from core.config import Config
    
    try:
        content_length = int(handler.headers['Content-Length'])
        payload = handler.rfile.read(content_length)
        sig_header = handler.headers.get('Stripe-Signature')
        
        is_production = Config.is_replit_deployment()
        if is_production:
            webhook_secret = Config.get_stripe_webhook_secret()
        else:
            webhook_secret = Config.get_test_stripe_webhook_secret()
        
        if not stripe_available:
            print("[STRIPE WEBHOOK] Stripe not available")
            handler.send_response(503)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Stripe not available'}).encode())
            return
        
        from stripe_client import verify_webhook_signature, get_subscription_details
        
        if webhook_secret and sig_header:
            event, error = verify_webhook_signature(payload, sig_header, webhook_secret)
            if error:
                print(f"[STRIPE WEBHOOK] Signature verification failed: {error}")
                handler.send_response(400)
                handler.send_header('Content-type', 'application/json')
                handler.end_headers()
                handler.wfile.write(json.dumps({'error': error}).encode())
                return
        else:
            try:
                event = json.loads(payload.decode('utf-8'))
                print(f"[STRIPE WEBHOOK] Warning: No webhook secret configured, skipping signature verification")
            except json.JSONDecodeError as e:
                handler.send_response(400)
                handler.send_header('Content-type', 'application/json')
                handler.end_headers()
                handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
                return
        
        event_type = event.get('type') if isinstance(event, dict) else event.type
        event_id = event.get('id') if isinstance(event, dict) else event.id
        event_data = event.get('data', {}).get('object', {}) if isinstance(event, dict) else event.data.object
        
        print(f"[STRIPE WEBHOOK] Received event: {event_type} ({event_id})")
        
        if event_id and db_module.is_webhook_event_processed(event_id):
            print(f"[STRIPE WEBHOOK] ⏭️ Event {event_id} already processed, skipping")
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'received': True, 'duplicate': True}).encode())
            return
        
        if event_type == 'checkout.session.completed':
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            customer_id = event_data.get('customer') if isinstance(event_data, dict) else getattr(event_data, 'customer', None)
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            amount_total = (event_data.get('amount_total') if isinstance(event_data, dict) else getattr(event_data, 'amount_total', 0)) or 0
            
            if subscription_id:
                sub_details = get_subscription_details(subscription_id)
                
                if sub_details:
                    price_id = sub_details.get('price_id') or get_subscription_price_id(event_data)
                    
                    tenant_id, vip_price_id, is_vip = resolve_tenant_and_vip_status(db_module, price_id, subscription_id)
                    
                    print(f"[STRIPE WEBHOOK] tenant={tenant_id}, price_id={price_id}, vip_price_id={vip_price_id}, is_vip={is_vip}")
                    
                    if not is_vip:
                        print(f"[STRIPE WEBHOOK] Subscription created but not VIP plan (price_id={price_id} != vip_price_id={vip_price_id}), skipping VIP grant")
                    else:
                        email = sub_details.get('email') or customer_email
                        name = sub_details.get('name')
                        amount_paid = sub_details.get('amount_paid') or (amount_total / 100)
                        plan_name = sub_details.get('plan_name') or 'premium'
                        
                        print(f"[STRIPE WEBHOOK] Creating VIP subscription: tenant={tenant_id}, email={email}, sub_id={subscription_id}, amount=${amount_paid}")
                        
                        result, error = db_module.create_or_update_telegram_subscription(
                            email=email,
                            tenant_id=tenant_id,
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id,
                            plan_type=plan_name,
                            amount_paid=amount_paid,
                            name=name
                        )
                        
                        if result:
                            print(f"[STRIPE WEBHOOK] ✅ VIP subscription created/updated: {email} (tenant={tenant_id})")
                        else:
                            print(f"[STRIPE WEBHOOK] ❌ Failed to create subscription: {error}")
                else:
                    print(f"[STRIPE WEBHOOK] Could not fetch subscription details for {subscription_id}")
            else:
                print(f"[STRIPE WEBHOOK] checkout.session.completed without subscription_id (one-time payment?)")
        
        elif event_type == 'customer.subscription.created':
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            
            price_id = get_subscription_price_id(event_data)
            tenant_id, vip_price_id, is_vip = resolve_tenant_and_vip_status(db_module, price_id, subscription_id)
            
            print(f"[STRIPE WEBHOOK] tenant={tenant_id}, price_id={price_id}, vip_price_id={vip_price_id}, is_vip={is_vip}")
            
            if not is_vip:
                print(f"[STRIPE WEBHOOK] customer.subscription.created but not VIP plan, skipping VIP grant")
            else:
                sub_details = get_subscription_details(subscription_id)
                if sub_details and sub_details.get('email'):
                    result, error = db_module.create_or_update_telegram_subscription(
                        email=sub_details['email'],
                        tenant_id=tenant_id,
                        stripe_customer_id=sub_details.get('customer_id'),
                        stripe_subscription_id=subscription_id,
                        plan_type=sub_details.get('plan_name') or 'premium',
                        amount_paid=sub_details.get('amount_paid', 0),
                        name=sub_details.get('name')
                    )
                    print(f"[STRIPE WEBHOOK] customer.subscription.created: {sub_details['email']} (tenant={tenant_id}) - {'success' if result else error}")
        
        elif event_type == 'customer.subscription.updated':
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            cancel_at_period_end = event_data.get('cancel_at_period_end') if isinstance(event_data, dict) else getattr(event_data, 'cancel_at_period_end', False)
            status = event_data.get('status') if isinstance(event_data, dict) else event_data.status
            
            tenant_id = db_module.get_tenant_id_by_subscription_id(subscription_id)
            if not tenant_id:
                price_id = get_subscription_price_id(event_data)
                tenant_id, _, _ = resolve_tenant_and_vip_status(db_module, price_id, subscription_id)
            
            print(f"[STRIPE WEBHOOK] customer.subscription.updated: {subscription_id}, status={status}, tenant={tenant_id}, cancel_at_period_end={cancel_at_period_end}")
            
            if status in ('past_due', 'unpaid', 'incomplete', 'incomplete_expired'):
                success, email, telegram_user_id = db_module.update_subscription_status(
                    tenant_id=tenant_id,
                    stripe_subscription_id=subscription_id,
                    status='payment_failed',
                    reason=f'stripe_status_{status}'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ⚠️ Marked subscription as payment_failed: {email} (tenant={tenant_id}, Stripe status: {status})")
                    
                    if telegram_user_id and telegram_bot_available:
                        private_channel_id = Config.get_forex_channel_id()
                        if private_channel_id:
                            try:
                                from telegram_bot import sync_kick_user_from_channel
                                kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                                print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id} due to {status}: {kicked}")
                            except Exception as kick_error:
                                print(f"[STRIPE WEBHOOK] Could not kick user: {kick_error}")
                else:
                    print(f"[STRIPE WEBHOOK] Could not find subscription {subscription_id} to update status")
            elif status == 'active':
                success, email, _ = db_module.update_subscription_status(
                    tenant_id=tenant_id,
                    stripe_subscription_id=subscription_id,
                    status='active',
                    reason='payment_succeeded'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ✅ Reactivated subscription: {email} (tenant={tenant_id})")
            else:
                sub_details = get_subscription_details(subscription_id)
                if sub_details and sub_details.get('email'):
                    print(f"[STRIPE WEBHOOK] Subscription {subscription_id} updated for {sub_details['email']} (tenant={tenant_id}, status: {status})")
        
        elif event_type == 'customer.subscription.deleted':
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            
            tenant_id = db_module.get_tenant_id_by_subscription_id(subscription_id)
            if not tenant_id:
                tenant_id = 'entrylab'
            
            print(f"[STRIPE WEBHOOK] customer.subscription.deleted: {subscription_id} (tenant={tenant_id})")
            
            sub_details = get_subscription_details(subscription_id)
            if sub_details and sub_details.get('email'):
                telegram_user_id = db_module.revoke_telegram_subscription(
                    sub_details['email'], 
                    tenant_id, 
                    'subscription_canceled'
                )
                print(f"[STRIPE WEBHOOK] Revoked access for {sub_details['email']} (tenant={tenant_id})")
                
                if telegram_user_id and telegram_bot_available:
                    private_channel_id = Config.get_forex_channel_id()
                    if private_channel_id:
                        from telegram_bot import sync_kick_user_from_channel
                        kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                        print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id}: {kicked}")
        
        elif event_type == 'customer.deleted':
            customer_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            customer_email = event_data.get('email') if isinstance(event_data, dict) else getattr(event_data, 'email', None)
            print(f"[STRIPE WEBHOOK] customer.deleted: {customer_id}, email={customer_email}")
            
            deleted = False
            if customer_id:
                deleted = db_module.delete_subscription_by_stripe_customer(customer_id)
            if not deleted and customer_email:
                deleted = db_module.delete_subscription_by_email(customer_email)
            
            if deleted:
                print(f"[STRIPE WEBHOOK] ✅ Deleted subscription record for customer {customer_id or customer_email}")
            else:
                print(f"[STRIPE WEBHOOK] No matching subscription found for customer {customer_id or customer_email}")
        
        elif event_type == 'invoice.paid':
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            amount_paid = (event_data.get('amount_paid') if isinstance(event_data, dict) else getattr(event_data, 'amount_paid', 0)) or 0
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            
            if subscription_id and amount_paid > 0:
                tenant_id = db_module.get_tenant_id_by_subscription_id(subscription_id)
                if not tenant_id:
                    tenant_id = 'entrylab'
                
                print(f"[STRIPE WEBHOOK] invoice.paid: {subscription_id}, amount=${amount_paid/100}, email={customer_email}, tenant={tenant_id}")
                
                success, email, _ = db_module.update_subscription_status(
                    tenant_id=tenant_id,
                    stripe_subscription_id=subscription_id,
                    status='active',
                    reason='invoice_paid'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ✅ Subscription reactivated after payment: {email} (tenant={tenant_id})")
        
        elif event_type == 'invoice.payment_failed':
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            attempt_count = event_data.get('attempt_count') if isinstance(event_data, dict) else getattr(event_data, 'attempt_count', 0)
            next_payment_attempt = event_data.get('next_payment_attempt') if isinstance(event_data, dict) else getattr(event_data, 'next_payment_attempt', None)
            
            if subscription_id:
                tenant_id = db_module.get_tenant_id_by_subscription_id(subscription_id)
                if not tenant_id:
                    tenant_id = 'entrylab'
                
                print(f"[STRIPE WEBHOOK] ⚠️ invoice.payment_failed: {subscription_id}, email={customer_email}, tenant={tenant_id}, attempt={attempt_count}")
                
                success, email, telegram_user_id = db_module.update_subscription_status(
                    tenant_id=tenant_id,
                    stripe_subscription_id=subscription_id,
                    status='payment_failed',
                    reason=f'invoice_payment_failed_attempt_{attempt_count}'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] Marked subscription as payment_failed: {email} (tenant={tenant_id})")
                    
                    if telegram_user_id and telegram_bot_available:
                        private_channel_id = Config.get_forex_channel_id()
                        if private_channel_id:
                            try:
                                from telegram_bot import sync_kick_user_from_channel
                                kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                                print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id} due to payment failure: {kicked}")
                            except Exception as kick_error:
                                print(f"[STRIPE WEBHOOK] Could not kick user: {kick_error}")
                            
                            try:
                                from telegram_bot import sync_send_message
                                retry_info = ""
                                if next_payment_attempt:
                                    from datetime import datetime
                                    retry_date = datetime.fromtimestamp(next_payment_attempt)
                                    retry_info = f"\n\nWe'll retry on {retry_date.strftime('%B %d, %Y')}."
                                
                                message = f"⚠️ **Payment Failed**\n\nYour VIP subscription payment could not be processed. Your access has been suspended until payment is resolved.\n\nPlease update your payment method to restore access.{retry_info}"
                                sync_send_message(telegram_user_id, message)
                                print(f"[STRIPE WEBHOOK] Sent payment failure notification to user {telegram_user_id}")
                            except Exception as notify_error:
                                print(f"[STRIPE WEBHOOK] Could not send notification: {notify_error}")
                else:
                    print(f"[STRIPE WEBHOOK] Could not find subscription {subscription_id} to mark as failed")
        
        if event_id:
            db_module.record_webhook_event_processed(event_id, event_source='stripe')
            print(f"[STRIPE WEBHOOK] ✅ Event {event_id} recorded as processed")
        
        import random
        if random.random() < 0.01:
            db_module.cleanup_old_webhook_events(hours=24)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'received': True}).encode())
        
    except Exception as e:
        print(f"[STRIPE WEBHOOK] ❌ Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
