"""
Subscription domain handlers.

Extracted from server.py - these handle Telegram subscription-related API endpoints.
"""
import json
import traceback
from urllib.parse import urlparse, parse_qs, unquote

from core.config import Config

from core.logging import get_logger
logger = get_logger(__name__)


def handle_telegram_check_access(handler):
    """GET /api/telegram/check-access/<email>"""
    import server
    parsed_path = urlparse(handler.path)
    
    api_key = handler.headers.get('X-API-Key') or handler.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = Config.get_entrylab_api_key()
    
    if not api_key or api_key != expected_key or not expected_key:
        handler.send_response(401)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'hasAccess': False, 'error': 'Unauthorized - Invalid API key'}).encode())
        return
    
    try:
        email = unquote(parsed_path.path.split('/api/telegram/check-access/')[1])
        
        if not email:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'hasAccess': False, 'error': 'Email parameter required'}).encode())
            return
        
        subscription = server.db.get_telegram_subscription_by_email(email, tenant_id=handler.tenant_id)
        
        if not subscription:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'hasAccess': False,
                'error': f'No subscription found for {email}'
            }).encode())
            return
        
        has_access = subscription['status'] == 'active' and subscription['telegram_user_id'] is not None
        
        response_data = {
            'hasAccess': has_access,
            'telegramUserId': subscription.get('telegram_user_id'),
            'telegramUsername': subscription.get('telegram_username'),
            'status': subscription.get('status'),
            'joinedAt': subscription.get('joined_at'),
            'lastSeenAt': subscription.get('last_seen_at')
        }
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(response_data).encode())
        
    except Exception as e:
        logger.exception("Error checking access")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'hasAccess': False, 'error': str(e)}).encode())


def handle_telegram_subscriptions(handler):
    """GET /api/telegram-subscriptions"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        status_filter = query_params.get('status', [None])[0]
        include_test = query_params.get('include_test', ['false'])[0].lower() == 'true'
        
        subscriptions = server.db.get_all_telegram_subscriptions(status_filter=status_filter, include_test=include_test, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'subscriptions': subscriptions}).encode())
    except Exception as e:
        logger.exception("Error getting subscriptions")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_telegram_revenue_metrics(handler):
    """GET /api/telegram/revenue-metrics"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        if not server.STRIPE_AVAILABLE:
            raise Exception("Stripe not configured")
        
        query_params = parse_qs(parsed_path.query)
        period = query_params.get('period', ['all'])[0]
        valid_periods = ['all', '30d', '7d', 'yesterday', 'today']
        if period not in valid_periods:
            period = 'all'
        
        subscriptions = server.db.get_all_telegram_subscriptions(tenant_id=handler.tenant_id)
        stripe_sub_ids = [s.get('stripe_subscription_id') for s in subscriptions if s.get('stripe_subscription_id')]
        
        from stripe_client import get_stripe_metrics
        
        logger.info(f"Fetching metrics for {len(stripe_sub_ids)} PromoStack subscriptions (period: {period})...")
        metrics = get_stripe_metrics(subscription_ids=stripe_sub_ids, period=period)
        
        if metrics:
            logger.info(f"Stripe returned: revenue=${metrics.get('total_revenue')}, rebill=${metrics.get('monthly_rebill')}")
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(metrics).encode())
        else:
            raise Exception("Failed to fetch metrics from Stripe")
        
    except Exception as e:
        logger.exception("Error getting metrics")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_telegram_conversion_analytics(handler):
    """GET /api/telegram/conversion-analytics"""
    import server
    
    try:
        analytics = server.db.get_conversion_analytics(tenant_id=handler.tenant_id)
        
        if analytics:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(analytics).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to fetch conversion analytics'}).encode())
        
    except Exception as e:
        logger.exception("Error getting analytics")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_telegram_billing(handler):
    """GET /api/telegram/billing/<subscription_id>"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        subscription_id = parsed_path.path.split('/api/telegram/billing/')[1]
        
        if not subscription_id:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Subscription ID required'}).encode())
            return
        
        subscription = server.db.get_telegram_subscription_by_id(int(subscription_id), tenant_id=handler.tenant_id)
        
        if not subscription:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Subscription not found'}).encode())
            return
        
        stripe_customer_id = subscription.get('stripe_customer_id')
        stripe_subscription_id = subscription.get('stripe_subscription_id')
        amount_paid = float(subscription.get('amount_paid') or 0)
        
        if amount_paid == 0:
            response_data = {
                'subscription': subscription,
                'billing': None,
                'billing_status': 'free_user'
            }
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(response_data).encode())
            return
        
        if not stripe_subscription_id and not stripe_customer_id:
            response_data = {
                'subscription': subscription,
                'billing': None,
                'billing_status': 'no_stripe_ids',
                'error': 'No Stripe subscription or customer ID linked'
            }
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(response_data).encode())
            return
        
        billing_info = None
        billing_error = None
        
        if stripe_subscription_id:
            try:
                from stripe_client import get_subscription_billing_info
                billing_info = get_subscription_billing_info(stripe_subscription_id)
                if billing_info and billing_info.get('error'):
                    billing_error = billing_info.get('error')
                    billing_info = None
            except Exception as stripe_err:
                logger.exception("Error fetching subscription from Stripe")
                billing_error = str(stripe_err)
        
        if not billing_info and stripe_customer_id:
            try:
                from stripe_client import get_customer_billing_info
                billing_info = get_customer_billing_info(stripe_customer_id)
                if billing_info and billing_info.get('error'):
                    billing_error = billing_info.get('error')
                    billing_info = None
            except Exception as stripe_err:
                logger.exception("Error fetching customer from Stripe")
                billing_error = str(stripe_err)
        
        if billing_info:
            response_data = {
                'subscription': subscription,
                'billing': billing_info,
                'billing_status': 'success'
            }
            handler.send_response(200)
        else:
            response_data = {
                'subscription': subscription,
                'billing': None,
                'billing_status': 'stripe_error',
                'error': billing_error or 'Unable to fetch billing info from Stripe'
            }
            handler.send_response(200)
        
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(response_data).encode())
        
    except Exception as e:
        logger.exception("Error getting billing info")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_telegram_grant_access(handler):
    """POST /api/telegram/grant-access"""
    import server
    
    api_key = handler.headers.get('X-API-Key') or handler.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = Config.get_entrylab_api_key()
    
    if not api_key or api_key != expected_key or not expected_key:
        handler.send_response(401)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - Invalid API key'}).encode())
        return
    
    if not server.TELEGRAM_BOT_AVAILABLE:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Telegram bot not available'}).encode())
        return
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        email = data.get('email')
        
        stripe_placeholders = {'', 'free', 'free_signup', 'test', 'null', 'none', 'n/a'}
        raw_customer_id = data.get('stripeCustomerId')
        raw_subscription_id = data.get('stripeSubscriptionId')
        stripe_customer_id = None if not raw_customer_id or str(raw_customer_id).lower().strip() in stripe_placeholders else raw_customer_id
        stripe_subscription_id = None if not raw_subscription_id or str(raw_subscription_id).lower().strip() in stripe_placeholders else raw_subscription_id
        user_id = data.get('userId')
        name = data.get('name')
        plan_type = data.get('planType', 'premium')
        
        utm_source = data.get('utmSource') or data.get('utm_source')
        utm_medium = data.get('utmMedium') or data.get('utm_medium')
        utm_campaign = data.get('utmCampaign') or data.get('utm_campaign')
        utm_content = data.get('utmContent') or data.get('utm_content')
        utm_term = data.get('utmTerm') or data.get('utm_term')
        
        raw_amount = data.get('amountPaid')
        if raw_amount is not None:
            amount_paid = float(raw_amount)
        elif 'free' in plan_type.lower():
            amount_paid = 0.0
        else:
            amount_paid = 49.00
        
        if not email:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Missing required field: email'}).encode())
            return
        
        is_free_user = amount_paid == 0 or 'free' in plan_type.lower()
        logger.info(f"Grant access request for {email}")
        logger.info(f"Data: plan={plan_type}, amount=${amount_paid}, free={is_free_user}")
        logger.info(f"Stripe: customer_id={stripe_customer_id}, subscription_id={stripe_subscription_id}")
        if utm_source or utm_campaign:
            logger.info(f"UTM: source={utm_source}, medium={utm_medium}, campaign={utm_campaign}")
        
        subscription, db_error = server.db.create_telegram_subscription(
            email=email,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            plan_type=plan_type,
            amount_paid=amount_paid,
            name=name,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            tenant_id=handler.tenant_id
        )
        
        if not subscription:
            error_msg = db_error or 'Failed to create subscription record'
            logger.error(f"Database error: {error_msg}")
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': error_msg}).encode())
            return
        
        if is_free_user:
            logger.info(f"Free lead captured for {email}")
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'inviteLink': None,
                'message': 'Free lead captured successfully',
                'isFreeUser': True
            }).encode())
            return
        
        private_channel_id = Config.get_forex_channel_id()
        if not private_channel_id:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'FOREX_CHANNEL_ID not configured'}).encode())
            return
        
        invite_link = server.telegram_bot.sync_create_private_channel_invite_link(private_channel_id)
        
        if not invite_link:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Failed to create invite link'}).encode())
            return
        
        server.db.update_telegram_subscription_invite(email, invite_link, tenant_id=handler.tenant_id)
        
        logger.info(f"Premium access granted for {email}, invite: {invite_link}")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'inviteLink': invite_link,
            'message': 'Premium access granted successfully',
            'isFreeUser': False
        }).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
    except Exception as e:
        logger.exception("Error granting access")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_clear_all(handler):
    """POST /api/telegram/clear-all"""
    import server
    
    api_key = handler.headers.get('X-API-Key') or handler.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = Config.get_entrylab_api_key()
    
    if not api_key or api_key != expected_key or not expected_key:
        handler.send_response(401)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
        return
    
    try:
        deleted = server.db.clear_all_telegram_subscriptions(tenant_id=handler.tenant_id)
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f'Cleared {deleted} subscription records'
        }).encode())
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_cleanup_test_data(handler):
    """POST /api/telegram/cleanup-test-data"""
    import server
    
    try:
        deleted_info = server.db.cleanup_test_telegram_subscriptions(tenant_id=handler.tenant_id)
        
        logger.info(f"Deleted {len(deleted_info)} test records: {deleted_info}")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f'Deleted {len(deleted_info)} test records',
            'deleted': deleted_info
        }).encode())
        
    except Exception as e:
        logger.exception("Cleanup error")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_cancel_subscription(handler):
    """POST /api/telegram/cancel-subscription"""
    import server
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        subscription_id = data.get('subscriptionId')
        cancel_immediately = data.get('cancelImmediately', False)
        
        if not subscription_id:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Missing subscriptionId'}).encode())
            return
        
        subscription = server.db.get_telegram_subscription_by_id(int(subscription_id), tenant_id=handler.tenant_id)
        
        if not subscription:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Subscription not found'}).encode())
            return
        
        stripe_subscription_id = subscription.get('stripe_subscription_id')
        
        if not stripe_subscription_id:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'No Stripe subscription linked to this record'}).encode())
            return
        
        logger.info(f"Canceling subscription {stripe_subscription_id} for user {subscription.get('email')}, immediately={cancel_immediately}")
        
        from stripe_client import cancel_subscription
        result = cancel_subscription(stripe_subscription_id, cancel_immediately=cancel_immediately)
        
        if result.get('success'):
            kicked_from_telegram = False
            if cancel_immediately:
                telegram_user_id = server.db.revoke_telegram_subscription(subscription.get('email'), 'admin_canceled', tenant_id=handler.tenant_id)
                
                if telegram_user_id and server.TELEGRAM_BOT_AVAILABLE:
                    private_channel_id = Config.get_forex_channel_id()
                    if private_channel_id:
                        from telegram_bot import sync_kick_user_from_channel
                        kicked_from_telegram = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                        if kicked_from_telegram:
                            logger.info(f"Kicked user {telegram_user_id} from Telegram channel")
                        else:
                            logger.warning(f"Failed to kick user {telegram_user_id} from Telegram channel")
                
                result['kicked_from_telegram'] = kicked_from_telegram
                result['message'] = 'Subscription canceled immediately' + (' and removed from Telegram channel' if kicked_from_telegram else '')
            
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(result).encode())
        else:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(result).encode())
            
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
    except Exception as e:
        logger.exception("Error canceling subscription")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_delete_subscription(handler):
    """POST /api/telegram/delete-subscription"""
    import server
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        subscription_id = data.get('subscriptionId')
        telegram_user_id = data.get('telegramUserId')
        
        if not subscription_id:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Missing subscriptionId'}).encode())
            return
        
        subscription = server.db.get_telegram_subscription_by_id(int(subscription_id), tenant_id=handler.tenant_id)
        if subscription:
            logger.info(f"Deleting subscription record: ID={subscription_id}, Email={subscription.get('email')}")
        
        kicked = False
        if telegram_user_id and server.TELEGRAM_BOT_AVAILABLE:
            private_channel_id = Config.get_forex_channel_id()
            if private_channel_id:
                from telegram_bot import sync_kick_user_from_channel
                kicked = sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                if kicked:
                    logger.info(f"Kicked user {telegram_user_id} from Telegram channel")
        
        deleted = server.db.delete_telegram_subscription(int(subscription_id), tenant_id=handler.tenant_id)
        
        if deleted:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'message': 'Subscription deleted successfully',
                'kicked_from_telegram': kicked
            }).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Subscription not found or already deleted'}).encode())
            
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
    except Exception as e:
        logger.exception("Error deleting subscription")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_revoke_access(handler):
    """POST /api/telegram/revoke-access"""
    import server
    
    api_key = handler.headers.get('X-API-Key') or handler.headers.get('Authorization', '').replace('Bearer ', '')
    expected_key = Config.get_entrylab_api_key()
    
    if not api_key or api_key != expected_key or not expected_key:
        handler.send_response(401)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - Invalid API key'}).encode())
        return
    
    if not server.TELEGRAM_BOT_AVAILABLE:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Telegram bot not available'}).encode())
        return
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        email = data.get('email')
        reason = data.get('reason', 'subscription_canceled')
        
        if not email:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Missing required field: email'}).encode())
            return
        
        logger.info(f"Revoke access request for {email}, reason: {reason}")
        
        subscription = server.db.get_telegram_subscription_by_email(email, tenant_id=handler.tenant_id)
        
        if not subscription:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': f'No subscription found for {email}'}).encode())
            return
        
        telegram_user_id = server.db.revoke_telegram_subscription(email, reason, tenant_id=handler.tenant_id)
        
        if telegram_user_id:
            private_channel_id = Config.get_forex_channel_id()
            if not private_channel_id:
                logger.warning("FOREX_CHANNEL_ID not configured, cannot kick user")
            else:
                kicked = server.telegram_bot.sync_kick_user_from_channel(private_channel_id, telegram_user_id)
                
                if kicked:
                    logger.info(f"User {telegram_user_id} kicked from channel")
                else:
                    logger.warning(f"Failed to kick user {telegram_user_id}")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f'Access revoked for {email}'
        }).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Invalid JSON format'}).encode())
    except Exception as e:
        logger.exception("Error revoking access")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_telegram_channel_stats(handler, tenant_id: str = None):
    """GET /api/telegram-channel-stats
    
    Returns channel stats using BotCredentialResolver for signal_bot.
    
    Returns:
        200: Success with member_count, channel_id, bot_username
        503: Bot not configured or channel_id missing
        502: Telegram API failure
    """
    import requests
    from core.logging import get_logger
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError, SIGNAL_BOT
    
    logger = get_logger(__name__)
    effective_tenant = tenant_id or 'entrylab'
    
    try:
        credentials = get_bot_credentials(effective_tenant, SIGNAL_BOT)
    except BotNotConfiguredError as e:
        logger.warning(f"Signal bot not configured for tenant {effective_tenant}: {e}")
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error_code': 'bot_not_configured',
            'message': f"Signal Bot not configured. Go to Connections → Signal Bot to set it up.",
            'tenant_id': effective_tenant,
            'bot_role': SIGNAL_BOT
        }).encode())
        return
    
    bot_token = credentials.get('bot_token')
    channel_id = credentials.get('channel_id')
    bot_username = credentials.get('bot_username')
    
    if not bot_token:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error_code': 'bot_token_missing',
            'message': "Signal Bot token missing. Go to Connections → Signal Bot to add it.",
            'tenant_id': effective_tenant,
            'bot_role': SIGNAL_BOT
        }).encode())
        return
    
    if not channel_id:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error_code': 'channel_id_missing',
            'message': "Signal Bot channel_id missing. Add it in Connections → Signal Bot.",
            'tenant_id': effective_tenant,
            'bot_role': SIGNAL_BOT,
            'bot_username': bot_username
        }).encode())
        return
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getChatMemberCount"
        resp = requests.get(url, params={'chat_id': channel_id}, timeout=10)
        data = resp.json()
        
        if data.get('ok'):
            member_count = data.get('result')
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'member_count': member_count,
                'channel_id': channel_id,
                'bot_username': bot_username,
                'tenant_id': effective_tenant
            }).encode())
        else:
            error_desc = data.get('description', 'Unknown Telegram error')
            error_code = data.get('error_code', 0)
            
            actionable_message = _get_actionable_telegram_error(error_desc)
            
            logger.warning(f"Telegram API error for channel {channel_id}: {error_desc}")
            handler.send_response(502)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': False,
                'error_code': 'telegram_api_error',
                'message': actionable_message,
                'telegram_error': error_desc,
                'telegram_error_code': error_code,
                'channel_id': channel_id,
                'bot_username': bot_username,
                'tenant_id': effective_tenant
            }).encode())
            
    except requests.Timeout:
        logger.warning(f"Telegram API timeout for channel {channel_id}")
        handler.send_response(502)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error_code': 'telegram_timeout',
            'message': "Telegram API timed out. Please try again.",
            'channel_id': channel_id,
            'tenant_id': effective_tenant
        }).encode())
    except Exception as e:
        logger.exception(f"Error getting channel stats for {effective_tenant}")
        handler.send_response(502)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error_code': 'telegram_api_error',
            'message': "Failed to contact Telegram API. Please try again.",
            'detail': str(e),
            'tenant_id': effective_tenant
        }).encode())


def _get_actionable_telegram_error(error_desc: str) -> str:
    """Map Telegram error descriptions to actionable user messages."""
    error_lower = error_desc.lower()
    
    if 'chat not found' in error_lower:
        return "Channel not found. Check the Channel ID format (should start with -100 for channels)."
    elif 'not enough rights' in error_lower or 'not a member' in error_lower:
        return "Bot doesn't have access. Add the bot to the channel and promote it to admin."
    elif 'bot was kicked' in error_lower or 'bot was blocked' in error_lower:
        return "Bot was removed from the channel. Re-add the bot and promote it to admin."
    elif 'invalid chat id' in error_lower or 'bad request' in error_lower:
        return "Invalid Channel ID format. Channel IDs for groups/channels should start with -100."
    elif 'unauthorized' in error_lower:
        return "Bot token is invalid. Check the token in Connections → Signal Bot."
    else:
        return f"Telegram error: {error_desc}"
