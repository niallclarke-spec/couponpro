"""
Stripe webhook HTTP handler.

Extracted from server.py - handles incoming Stripe webhook POST requests.
Handler receives dependencies as parameters to avoid stale module globals.
"""
import json


def handle_stripe_webhook(handler, stripe_available, telegram_bot_available, db_module):
    """POST /api/stripe/webhook - Stripe webhook handler
    
    Args:
        handler: HTTP request handler
        stripe_available: STRIPE_AVAILABLE flag
        telegram_bot_available: TELEGRAM_BOT_AVAILABLE flag
        db_module: Database module for idempotency and subscription updates
    """
    from core.config import Config
    
    # Stripe Webhook - Handle subscription events automatically
    # No auth required - uses Stripe signature verification
    try:
        content_length = int(handler.headers['Content-Length'])
        payload = handler.rfile.read(content_length)
        sig_header = handler.headers.get('Stripe-Signature')
        
        # Use test webhook secret in dev mode, live secret in production
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
        
        # If webhook secret is configured, verify signature
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
            # No webhook secret - parse event directly (less secure, for development)
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
        
        # Idempotency check - skip if we've already processed this event
        if event_id and db_module.is_webhook_event_processed(event_id):
            print(f"[STRIPE WEBHOOK] ⏭️ Event {event_id} already processed, skipping")
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'received': True, 'duplicate': True}).encode())
            return
        
        # Handle different event types
        if event_type == 'checkout.session.completed':
            # New subscription payment completed
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            customer_id = event_data.get('customer') if isinstance(event_data, dict) else getattr(event_data, 'customer', None)
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            amount_total = (event_data.get('amount_total') if isinstance(event_data, dict) else getattr(event_data, 'amount_total', 0)) or 0
            
            if subscription_id:
                # Get full subscription details from Stripe
                sub_details = get_subscription_details(subscription_id)
                
                if sub_details:
                    email = sub_details.get('email') or customer_email
                    name = sub_details.get('name')
                    amount_paid = sub_details.get('amount_paid') or (amount_total / 100)
                    plan_name = sub_details.get('plan_name') or 'premium'
                    
                    print(f"[STRIPE WEBHOOK] Creating subscription: email={email}, sub_id={subscription_id}, amount=${amount_paid}")
                    
                    # Create or update subscription in database
                    result, error = db_module.create_or_update_telegram_subscription(
                        email=email,
                        stripe_customer_id=customer_id,
                        stripe_subscription_id=subscription_id,
                        plan_type=plan_name,
                        amount_paid=amount_paid,
                        name=name
                    )
                    
                    if result:
                        print(f"[STRIPE WEBHOOK] ✅ Subscription created/updated: {email}")
                    else:
                        print(f"[STRIPE WEBHOOK] ❌ Failed to create subscription: {error}")
                else:
                    print(f"[STRIPE WEBHOOK] Could not fetch subscription details for {subscription_id}")
            else:
                print(f"[STRIPE WEBHOOK] checkout.session.completed without subscription_id (one-time payment?)")
        
        elif event_type == 'customer.subscription.created':
            # Subscription created
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            
            sub_details = get_subscription_details(subscription_id)
            if sub_details and sub_details.get('email'):
                result, error = db_module.create_or_update_telegram_subscription(
                    email=sub_details['email'],
                    stripe_customer_id=sub_details.get('customer_id'),
                    stripe_subscription_id=subscription_id,
                    plan_type=sub_details.get('plan_name') or 'premium',
                    amount_paid=sub_details.get('amount_paid', 0),
                    name=sub_details.get('name')
                )
                print(f"[STRIPE WEBHOOK] customer.subscription.created: {sub_details['email']} - {'success' if result else error}")
        
        elif event_type == 'customer.subscription.updated':
            # Subscription updated (e.g., plan change, cancellation scheduled, payment failure)
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            cancel_at_period_end = event_data.get('cancel_at_period_end') if isinstance(event_data, dict) else getattr(event_data, 'cancel_at_period_end', False)
            status = event_data.get('status') if isinstance(event_data, dict) else event_data.status
            
            print(f"[STRIPE WEBHOOK] customer.subscription.updated: {subscription_id}, status={status}, cancel_at_period_end={cancel_at_period_end}")
            
            # Handle payment failure states - update subscription status and revoke access
            if status in ('past_due', 'unpaid', 'incomplete', 'incomplete_expired'):
                success, email, telegram_user_id = db_module.update_subscription_status(
                    stripe_subscription_id=subscription_id,
                    status='payment_failed',
                    reason=f'stripe_status_{status}'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ⚠️ Marked subscription as payment_failed: {email} (Stripe status: {status})")
                    
                    # Kick user from Telegram channel
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
                # Payment succeeded - reactivate subscription if it was failed
                success, email, _ = db_module.update_subscription_status(
                    stripe_subscription_id=subscription_id,
                    status='active',
                    reason='payment_succeeded'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ✅ Reactivated subscription: {email}")
            else:
                # Other status - just log
                sub_details = get_subscription_details(subscription_id)
                if sub_details and sub_details.get('email'):
                    print(f"[STRIPE WEBHOOK] Subscription {subscription_id} updated for {sub_details['email']} (status: {status})")
        
        elif event_type == 'customer.subscription.deleted':
            # Subscription canceled/ended
            subscription_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            print(f"[STRIPE WEBHOOK] customer.subscription.deleted: {subscription_id}")
            
            sub_details = get_subscription_details(subscription_id)
            if sub_details and sub_details.get('email'):
                # Revoke access in database
                telegram_user_id = db_module.revoke_telegram_subscription(sub_details['email'], 'subscription_canceled')
                print(f"[STRIPE WEBHOOK] Revoked access for {sub_details['email']}")
                
                # Kick from Telegram if configured
                if telegram_user_id and telegram_bot_available:
                    private_channel_id = Config.get_forex_channel_id()
                    if private_channel_id:
                        from telegram_bot import sync_kick_user_from_channel
                        kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                        print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id}: {kicked}")
        
        elif event_type == 'customer.deleted':
            # Customer deleted from Stripe - delete from our database too
            customer_id = event_data.get('id') if isinstance(event_data, dict) else event_data.id
            customer_email = event_data.get('email') if isinstance(event_data, dict) else getattr(event_data, 'email', None)
            print(f"[STRIPE WEBHOOK] customer.deleted: {customer_id}, email={customer_email}")
            
            # Try to find and delete by customer ID first, then by email
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
            # Invoice paid - update amount_paid for renewals
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            amount_paid = (event_data.get('amount_paid') if isinstance(event_data, dict) else getattr(event_data, 'amount_paid', 0)) or 0
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            
            if subscription_id and amount_paid > 0:
                print(f"[STRIPE WEBHOOK] invoice.paid: {subscription_id}, amount=${amount_paid/100}, email={customer_email}")
                # Reactivate subscription if it was previously failed
                success, email, _ = db_module.update_subscription_status(
                    stripe_subscription_id=subscription_id,
                    status='active',
                    reason='invoice_paid'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] ✅ Subscription reactivated after payment: {email}")
        
        elif event_type == 'invoice.payment_failed':
            # Invoice payment failed - mark subscription as payment_failed and revoke access
            subscription_id = event_data.get('subscription') if isinstance(event_data, dict) else getattr(event_data, 'subscription', None)
            customer_email = event_data.get('customer_email') if isinstance(event_data, dict) else getattr(event_data, 'customer_email', None)
            attempt_count = event_data.get('attempt_count') if isinstance(event_data, dict) else getattr(event_data, 'attempt_count', 0)
            next_payment_attempt = event_data.get('next_payment_attempt') if isinstance(event_data, dict) else getattr(event_data, 'next_payment_attempt', None)
            
            print(f"[STRIPE WEBHOOK] ⚠️ invoice.payment_failed: {subscription_id}, email={customer_email}, attempt={attempt_count}")
            
            if subscription_id:
                success, email, telegram_user_id = db_module.update_subscription_status(
                    stripe_subscription_id=subscription_id,
                    status='payment_failed',
                    reason=f'invoice_payment_failed_attempt_{attempt_count}'
                )
                if success:
                    print(f"[STRIPE WEBHOOK] Marked subscription as payment_failed: {email}")
                    
                    # Kick user from Telegram channel on payment failure
                    if telegram_user_id and telegram_bot_available:
                        private_channel_id = Config.get_forex_channel_id()
                        if private_channel_id:
                            try:
                                from telegram_bot import sync_kick_user_from_channel
                                kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                                print(f"[STRIPE WEBHOOK] Kicked user {telegram_user_id} due to payment failure: {kicked}")
                            except Exception as kick_error:
                                print(f"[STRIPE WEBHOOK] Could not kick user: {kick_error}")
                            
                            # Send notification about failed payment
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
        
        # Record this event as processed to prevent duplicate handling
        if event_id:
            db_module.record_webhook_event_processed(event_id, event_source='stripe')
            print(f"[STRIPE WEBHOOK] ✅ Event {event_id} recorded as processed")
        
        # Periodically cleanup old events (every ~100 requests)
        import random
        if random.random() < 0.01:  # 1% chance
            db_module.cleanup_old_webhook_events(hours=24)
        
        # Always return 200 to acknowledge receipt
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'received': True}).encode())
        
    except Exception as e:
        # Return 500 for processing errors to allow Stripe retries
        # The idempotency table prevents duplicate processing on retry
        print(f"[STRIPE WEBHOOK] ❌ Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        # Return 500 so Stripe will retry (idempotency handles duplicates)
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
