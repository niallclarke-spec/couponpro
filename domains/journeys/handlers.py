"""
Journey API handlers.
"""
import json
from urllib.parse import urlparse, parse_qs
from core.logging import get_logger

logger = get_logger(__name__)


def handle_journeys_list(handler):
    """GET /api/journeys - List all journeys for tenant."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
        journeys = repo.list_journeys(tenant_id)
        
        for j in journeys:
            j['triggers'] = repo.get_triggers(tenant_id, j['id'])
            steps = repo.list_steps(tenant_id, j['id'])
            j['step_count'] = len(steps)
        
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
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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


def handle_journey_create(handler):
    """POST /api/journeys - Create a new journey."""
    from . import repo
    
    try:
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
        
        steps = data.get('steps', [])
        
        success = repo.set_steps(tenant_id, journey_id, steps)
        
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
        
        tenant_id = getattr(handler, 'tenant_id', 'entrylab')
        
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
