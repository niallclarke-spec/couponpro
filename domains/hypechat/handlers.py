"""
Hype Chat HTTP Handlers - Thin handlers that delegate to service/repo.
"""
import json
from urllib.parse import urlparse
from core.logging import get_logger
from domains.hypechat import repo, service

logger = get_logger(__name__)


def _send_no_tenant_context(handler):
    handler.send_response(403)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'error': 'No tenant context available'}).encode())


def _send_json(handler, status: int, data: dict):
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _read_json_body(handler) -> dict:
    content_length = int(handler.headers.get('Content-Length', 0))
    if content_length == 0:
        return {}
    body = handler.rfile.read(content_length)
    return json.loads(body.decode('utf-8'))


def handle_list_prompts(handler):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    prompts = repo.list_prompts(tenant_id)
    _send_json(handler, 200, {"prompts": prompts})


def handle_create_prompt(handler):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    name = data.get('name', '').strip()
    custom_prompt = data.get('custom_prompt', '').strip()

    if not name or not custom_prompt:
        _send_json(handler, 400, {"error": "name and custom_prompt are required"})
        return

    prompt = repo.create_prompt(tenant_id, name, custom_prompt)
    if prompt:
        _send_json(handler, 201, prompt)
    else:
        _send_json(handler, 500, {"error": "Failed to create prompt"})


def handle_update_prompt(handler, prompt_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    name = data.get('name', '').strip()
    custom_prompt = data.get('custom_prompt', '').strip()

    if not name or not custom_prompt:
        _send_json(handler, 400, {"error": "name and custom_prompt are required"})
        return

    prompt = repo.update_prompt(tenant_id, prompt_id, name, custom_prompt)
    if prompt:
        _send_json(handler, 200, prompt)
    else:
        _send_json(handler, 404, {"error": "Prompt not found"})


def handle_delete_prompt(handler, prompt_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    if repo.delete_prompt(tenant_id, prompt_id):
        _send_json(handler, 200, {"success": True})
    else:
        _send_json(handler, 404, {"error": "Prompt not found"})


def handle_list_flows(handler):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    flows = repo.list_flows(tenant_id)
    _send_json(handler, 200, {"flows": flows})


def handle_create_flow(handler):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    name = data.get('name', '').strip()
    prompt_id = data.get('prompt_id')

    if not name:
        _send_json(handler, 400, {"error": "name is required"})
        return

    flow = repo.create_flow(
        tenant_id=tenant_id,
        prompt_id=prompt_id,
        name=name,
        message_count=data.get('message_count', 3),
        interval_minutes=data.get('interval_minutes', 90),
        delay_after_cta_minutes=data.get('delay_after_cta_minutes', 10),
        active_days=data.get('active_days', 'mon-fri'),
    )
    if flow:
        _send_json(handler, 201, flow)
    else:
        _send_json(handler, 500, {"error": "Failed to create flow"})


def handle_update_flow(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    flow = repo.update_flow(tenant_id, flow_id, data)
    if flow:
        _send_json(handler, 200, flow)
    else:
        _send_json(handler, 404, {"error": "Flow not found"})


def handle_delete_flow(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    if repo.delete_flow(tenant_id, flow_id):
        _send_json(handler, 200, {"success": True})
    else:
        _send_json(handler, 404, {"error": "Flow not found"})


def handle_set_flow_status(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    status = data.get('status', '').strip()

    if status not in ('active', 'paused'):
        _send_json(handler, 400, {"error": "status must be 'active' or 'paused'"})
        return

    if repo.set_flow_status(tenant_id, flow_id, status):
        _send_json(handler, 200, {"success": True, "status": status})
    else:
        _send_json(handler, 404, {"error": "Flow not found"})


def handle_preview_message(handler):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    data = _read_json_body(handler)
    custom_prompt = data.get('custom_prompt', '').strip()
    message_count = int(data.get('message_count', 3))

    if not custom_prompt:
        _send_json(handler, 400, {"error": "custom_prompt is required"})
        return

    if message_count < 1 or message_count > 10:
        message_count = 3

    result = service.preview_message(tenant_id, custom_prompt, message_count)
    _send_json(handler, 200, result)


def handle_trigger_flow(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    result = service.execute_flow(tenant_id, flow_id)
    status_code = 200 if result.get("success") else 400
    _send_json(handler, status_code, result)


def handle_flow_analytics(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return

    messages = repo.get_flow_messages(tenant_id, flow_id, limit=50)
    today_count = repo.get_today_hype_count(tenant_id)

    _send_json(handler, 200, {
        "flow": flow,
        "messages": messages,
        "today_message_count": today_count,
        "total_messages": len(messages),
    })
