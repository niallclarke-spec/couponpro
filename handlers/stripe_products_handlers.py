"""
Stripe products domain handlers.

Handles Stripe product/price management API endpoints:
- GET /api/stripe/status - Check Stripe connection status
- POST /api/stripe/sync-products - Sync products from Stripe
- GET /api/stripe/products - List cached products/prices
- POST /api/stripe/set-vip-price - Set VIP plan price
"""
import json
import db

from core.logging import get_logger
logger = get_logger(__name__)


def _send_json_response(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _get_tenant_id_from_handler(handler) -> str:
    """Extract tenant_id from handler (set by middleware)."""
    return getattr(handler, 'tenant_id', None)


def handle_stripe_status(handler):
    """GET /api/stripe/status - Get Stripe connection status for tenant."""
    try:
        tenant_id = _get_tenant_id_from_handler(handler)
        if not tenant_id:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return
        
        integration = db.get_tenant_integration(tenant_id, 'stripe')
        settings = db.get_tenant_stripe_settings(tenant_id)
        products = db.get_tenant_stripe_products(tenant_id)
        
        connected = integration is not None
        method = None
        if connected:
            if integration.get('stripe_connect_account_id'):
                method = 'connect'
            elif integration.get('secret_key'):
                method = 'direct'
        
        product_count = len(products)
        price_count = sum(len(p.get('prices', [])) for p in products)
        
        response = {
            'connected': connected,
            'method': method,
            'last_sync_at': settings.get('stripe_last_sync_at') if settings else None,
            'vip_price_id': settings.get('vip_price_id') if settings else None,
            'vip_product_id': settings.get('vip_product_id') if settings else None,
            'product_count': product_count,
            'price_count': price_count
        }
        
        _send_json_response(handler, 200, response)
        
    except Exception as e:
        logger.exception("Error getting stripe status")
        _send_json_response(handler, 500, {'error': str(e)})


def handle_stripe_sync_products(handler):
    """POST /api/stripe/sync-products - Sync products from Stripe API."""
    try:
        tenant_id = _get_tenant_id_from_handler(handler)
        if not tenant_id:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return
        
        from integrations.stripe.tenant_client import get_tenant_stripe_client
        
        client, error = get_tenant_stripe_client(tenant_id)
        if not client:
            _send_json_response(handler, 400, {'success': False, 'error': error or 'Stripe not connected'})
            return
        
        products_data, error = client.list_products(active_only=True)
        if error:
            _send_json_response(handler, 500, {'success': False, 'error': f'Failed to fetch products: {error}'})
            return
        
        prices_data, error = client.list_prices(active_only=True)
        if error:
            _send_json_response(handler, 500, {'success': False, 'error': f'Failed to fetch prices: {error}'})
            return
        
        db.clear_tenant_stripe_cache(tenant_id)
        
        products_synced = 0
        for product in products_data:
            product_id = product.id
            name = product.name
            description = product.description
            active = product.active
            metadata = dict(product.metadata) if product.metadata else {}
            
            if db.upsert_tenant_stripe_product(tenant_id, product_id, name, description, active, metadata):
                products_synced += 1
        
        prices_synced = 0
        for price in prices_data:
            price_id = price.id
            product_id = price.product if isinstance(price.product, str) else price.product.id
            currency = price.currency
            unit_amount = price.unit_amount
            recurring_interval = None
            recurring_interval_count = 1
            price_type = 'one_time'
            
            if price.recurring:
                recurring_interval = price.recurring.interval
                recurring_interval_count = price.recurring.interval_count or 1
                price_type = 'recurring'
            
            nickname = price.nickname
            active = price.active
            
            if db.upsert_tenant_stripe_price(
                tenant_id, price_id, product_id, currency, unit_amount,
                recurring_interval, recurring_interval_count, nickname, active, price_type
            ):
                prices_synced += 1
        
        db.update_stripe_sync_timestamp(tenant_id)
        
        logger.info(f"Stripe sync completed for tenant {tenant_id}: {products_synced} products, {prices_synced} prices")
        
        _send_json_response(handler, 200, {
            'success': True,
            'products_synced': products_synced,
            'prices_synced': prices_synced
        })
        
    except Exception as e:
        logger.exception("Error syncing stripe products")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})


def handle_stripe_products(handler):
    """GET /api/stripe/products - Get cached products with prices for tenant."""
    try:
        tenant_id = _get_tenant_id_from_handler(handler)
        if not tenant_id:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return
        
        products = db.get_tenant_stripe_products(tenant_id)
        settings = db.get_tenant_stripe_settings(tenant_id)
        vip_price_id = settings.get('vip_price_id') if settings else None
        
        for product in products:
            for price in product.get('prices', []):
                price['is_vip_plan'] = price.get('price_id') == vip_price_id
        
        _send_json_response(handler, 200, {
            'products': products,
            'vip_price_id': vip_price_id
        })
        
    except Exception as e:
        logger.exception("Error getting stripe products")
        _send_json_response(handler, 500, {'error': str(e)})


def handle_stripe_set_vip_price(handler):
    """POST /api/stripe/set-vip-price - Set VIP plan price for tenant."""
    try:
        tenant_id = _get_tenant_id_from_handler(handler)
        if not tenant_id:
            _send_json_response(handler, 401, {'error': 'Authentication required'})
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length == 0:
            _send_json_response(handler, 400, {'success': False, 'error': 'Request body required'})
            return
        
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        price_id = data.get('price_id', '').strip()
        if not price_id:
            _send_json_response(handler, 400, {'success': False, 'error': 'price_id is required'})
            return
        
        products = db.get_tenant_stripe_products(tenant_id)
        price_details = None
        product_id = None
        
        for product in products:
            for price in product.get('prices', []):
                if price.get('price_id') == price_id:
                    price_details = price
                    product_id = product.get('product_id')
                    break
            if price_details:
                break
        
        if not price_details:
            _send_json_response(handler, 404, {'success': False, 'error': 'Price not found in tenant products'})
            return
        
        if not db.save_tenant_stripe_settings(tenant_id, vip_product_id=product_id, vip_price_id=price_id):
            _send_json_response(handler, 500, {'success': False, 'error': 'Failed to save settings'})
            return
        
        logger.info(f"Set VIP price for tenant {tenant_id}: price_id={price_id}, product_id={product_id}")
        
        _send_json_response(handler, 200, {
            'success': True,
            'vip_price_id': price_id,
            'vip_product_id': product_id,
            'price_details': price_details
        })
        
    except json.JSONDecodeError:
        _send_json_response(handler, 400, {'success': False, 'error': 'Invalid JSON'})
    except Exception as e:
        logger.exception("Error setting VIP price")
        _send_json_response(handler, 500, {'success': False, 'error': str(e)})
