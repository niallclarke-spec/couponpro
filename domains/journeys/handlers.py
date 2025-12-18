"""
Journey API handlers.
"""
import json
from urllib.parse import urlparse, parse_qs
from core.logging import get_logger

logger = get_logger(__name__)


def _send_no_tenant_context(handler):
    """Send 403 when tenant context is missing."""
    handler.send_response(403)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'error': 'No tenant context available'}).encode())


def handle_journeys_list(handler):
    """GET /api/journeys - List all journeys for tenant."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        # Use optimized batched query (2 queries instead of 2N+1)
        journeys = repo.list_journeys_with_summary(tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'journeys': journeys}).encode())
    except Exception as e:
        logger.exception(f"Error listing journeys: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_get(handler, journey_id: str):
    """GET /api/journeys/:id - Get a specific journey."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        journey = repo.get_journey(tenant_id, journey_id)
        
        if not journey:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
            return
        
        journey['triggers'] = repo.get_triggers(tenant_id, journey_id)
        journey['steps'] = repo.list_steps(tenant_id, journey_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'journey': journey}).encode())
    except Exception as e:
        logger.exception(f"Error getting journey: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


MAX_JOURNEYS_PER_TENANT = 6


def handle_journey_create(handler):
    """POST /api/journeys - Create a new journey."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        current_count = repo.count_journeys(tenant_id)
        if current_count >= MAX_JOURNEYS_PER_TENANT:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'error': f'Maximum of {MAX_JOURNEYS_PER_TENANT} journeys allowed per tenant'
            }).encode())
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        name = data.get('name')
        if not name:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'name is required'}).encode())
            return
        
        bot_id = data.get('bot_id', 'default')
        description = data.get('description', '')
        status = data.get('status', 'draft')
        re_entry_policy = data.get('re_entry_policy', 'block')
        
        journey = repo.create_journey(
            tenant_id=tenant_id,
            bot_id=bot_id,
            name=name,
            description=description,
            status=status,
            re_entry_policy=re_entry_policy
        )
        
        if journey:
            handler.send_response(201)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'journey': journey}).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to create journey'}).encode())
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception(f"Error creating journey: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_update(handler, journey_id: str):
    """PUT /api/journeys/:id - Update a journey."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        journey = repo.update_journey(tenant_id, journey_id, data)
        
        if journey:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'journey': journey}).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception(f"Error updating journey: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_triggers(handler, journey_id: str):
    """POST /api/journeys/:id/triggers - Create or update a trigger."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        journey = repo.get_journey(tenant_id, journey_id)
        if not journey:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        trigger_type = data.get('trigger_type', 'telegram_deeplink')
        trigger_config = data.get('trigger_config', {})
        is_active = data.get('is_active', True)
        
        trigger = repo.upsert_trigger(tenant_id, journey_id, trigger_type, trigger_config, is_active)
        
        if trigger:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'trigger': trigger}).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to create trigger'}).encode())
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception(f"Error creating trigger: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_steps_get(handler, journey_id: str):
    """GET /api/journeys/:id/steps - Get journey steps."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        journey = repo.get_journey(tenant_id, journey_id)
        if not journey:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
            return
        
        steps = repo.list_steps(tenant_id, journey_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'steps': steps}).encode())
    except Exception as e:
        logger.exception(f"Error getting steps: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_steps_set(handler, journey_id: str):
    """PUT /api/journeys/:id/steps - Replace all steps."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        journey = repo.get_journey(tenant_id, journey_id)
        if not journey:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
            return
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        raw_steps = data.get('steps', [])
        
        normalized_steps = []
        for i, step in enumerate(raw_steps):
            text = step.get('message_template') or step.get('text') or step.get('config', {}).get('text', '')
            delay = step.get('delay_seconds', 0)
            if isinstance(delay, str):
                delay = int(delay) if delay.isdigit() else 0
            
            wait_for_reply = step.get('wait_for_reply', False)
            timeout_action = step.get('timeout_action', 'continue')
            
            if wait_for_reply:
                step_type = 'wait_for_reply'
            elif delay > 0:
                step_type = 'delay'
            else:
                step_type = 'message'
            
            timeout_minutes = 0
            if wait_for_reply and delay > 0:
                timeout_minutes = max(1, delay // 60)
            
            normalized_steps.append({
                'step_order': step.get('step_order', i + 1),
                'step_type': step_type,
                'config': {
                    'text': text,
                    'delay_seconds': delay,
                    'wait_for_reply': wait_for_reply,
                    'timeout_action': timeout_action,
                    'timeout_minutes': timeout_minutes
                }
            })
        
        logger.info(f"Saving {len(normalized_steps)} steps for journey {journey_id}: {[s['config'].get('text', '')[:50] for s in normalized_steps]}")
        
        success = repo.set_steps(tenant_id, journey_id, normalized_steps)
        
        if success:
            updated_steps = repo.list_steps(tenant_id, journey_id)
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'steps': updated_steps}).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Failed to set steps'}).encode())
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Invalid JSON'}).encode())
    except Exception as e:
        logger.exception(f"Error setting steps: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_sessions_debug(handler):
    """GET /api/journeys/debug/sessions - List sessions for debugging.
    
    Admin-only endpoint. Uses handler.tenant_id for tenant scoping.
    Admins can optionally pass ?all=true to see all tenants.
    """
    from . import repo
    from auth.clerk_auth import is_admin_email
    
    try:
        parsed_path = urlparse(handler.path)
        query_params = parse_qs(parsed_path.query)
        
        limit = int(query_params.get('limit', [50])[0])
        
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        show_all = query_params.get('all', ['false'])[0].lower() == 'true'
        clerk_email = getattr(handler, 'clerk_email', None)
        if show_all and clerk_email and is_admin_email(clerk_email):
            tenant_id = None
        
        sessions = repo.list_sessions_debug(tenant_id=tenant_id, limit=limit)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'sessions': sessions}).encode())
    except Exception as e:
        logger.exception(f"Error listing sessions: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_journey_delete(handler, journey_id: str):
    """DELETE /api/journeys/:id - Delete a journey."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', None)
        if not tenant_id:
            _send_no_tenant_context(handler)
            return
        
        success = repo.delete_journey(tenant_id, journey_id)
        
        if success:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': True}).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Journey not found'}).encode())
    except Exception as e:
        logger.exception(f"Error deleting journey: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
