"""
Hype Chat HTTP Handlers - Thin handlers that delegate to service/repo.
"""
import json
from urllib.parse import urlparse
from core.logging import get_logger
from domains.hypechat import repo, service

logger = get_logger(__name__)


ALL_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DAY_LABELS = {'mon': 'Mon', 'tue': 'Tue', 'wed': 'Wed', 'thu': 'Thu', 'fri': 'Fri', 'sat': 'Sat', 'sun': 'Sun'}



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

    active_days = data.get('active_days', 'mon-fri')

    flow = repo.create_flow(
        tenant_id=tenant_id,
        prompt_id=prompt_id,
        name=name,
        message_count=data.get('message_count', 3),
        interval_minutes=data.get('interval_minutes', 90),
        interval_max_minutes=data.get('interval_max_minutes', data.get('interval_minutes', 90)),
        delay_after_cta_minutes=data.get('delay_after_cta_minutes', 10),
        active_days=active_days,
        cta_enabled=data.get('cta_enabled', False),
        cta_delay_minutes=data.get('cta_delay_minutes', 30),
        cta_intro_text=data.get('cta_intro_text', ''),
        cta_vip_label=data.get('cta_vip_label', ''),
        cta_vip_url=data.get('cta_vip_url', ''),
        cta_support_label=data.get('cta_support_label', ''),
        cta_support_url=data.get('cta_support_url', ''),
        bump_enabled=data.get('bump_enabled', False),
        bump_preset=data.get('bump_preset'),
        bump_delay_minutes=data.get('bump_delay_minutes', 0),
        trigger_after_flow_id=data.get('trigger_after_flow_id'),
        trigger_delay_minutes=data.get('trigger_delay_minutes', 0),
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

    result = service.execute_flow(tenant_id, flow_id, skip_day_check=True)
    status_code = 200 if result.get("success") else 400
    _send_json(handler, status_code, result)


def handle_list_steps(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    steps = repo.list_steps(flow_id)
    _send_json(handler, 200, {"steps": steps})


def _validate_step_data(data: dict) -> str:
    step_type = data.get('step_type', '')
    if step_type not in ('reforward', 'cta', 'message', 'ai_hype'):
        return "step_type must be one of: reforward, cta, message, ai_hype"
    if step_type == 'reforward':
        preset = data.get('reforward_preset', '')
        if preset not in ('best_tp', 'daily_recap', 'weekly_recap', 'signal'):
            return "reforward_preset must be one of: best_tp, daily_recap, weekly_recap, signal"
    if step_type == 'cta':
        if not data.get('cta_vip_label') and not data.get('cta_support_label'):
            return "CTA step requires at least one link (VIP or Support)"
    if step_type == 'message':
        if not data.get('message_text', '').strip():
            return "message step requires message_text"
    return ""


def handle_create_step(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    data = _read_json_body(handler)
    err = _validate_step_data(data)
    if err:
        _send_json(handler, 400, {"error": err})
        return
    existing = repo.list_steps(flow_id)
    next_order = max((s['step_order'] for s in existing), default=-1) + 1
    step = repo.create_step(
        flow_id=flow_id,
        step_order=next_order,
        delay_minutes=int(data.get('delay_minutes', 0)),
        step_type=data['step_type'],
        reforward_preset=data.get('reforward_preset'),
        message_text=data.get('message_text', ''),
        cta_intro_text=data.get('cta_intro_text', ''),
        cta_vip_label=data.get('cta_vip_label', ''),
        cta_vip_url=data.get('cta_vip_url', ''),
        cta_support_label=data.get('cta_support_label', ''),
        cta_support_url=data.get('cta_support_url', ''),
    )
    if step:
        _send_json(handler, 201, step)
    else:
        _send_json(handler, 500, {"error": "Failed to create step"})


def handle_update_step(handler, flow_id: str, step_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    data = _read_json_body(handler)
    allowed = {'delay_minutes', 'step_type', 'reforward_preset', 'message_text',
               'cta_intro_text', 'cta_vip_label', 'cta_vip_url',
               'cta_support_label', 'cta_support_url'}
    update_data = {k: v for k, v in data.items() if k in allowed}
    step = repo.update_step(step_id, flow_id, **update_data)
    if step:
        _send_json(handler, 200, step)
    else:
        _send_json(handler, 404, {"error": "Step not found"})


def handle_delete_step(handler, flow_id: str, step_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    if repo.delete_step(step_id, flow_id):
        _send_json(handler, 200, {"success": True})
    else:
        _send_json(handler, 404, {"error": "Step not found"})


def handle_reorder_steps(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    data = _read_json_body(handler)
    ordered_ids = data.get('ordered_ids', [])
    if not ordered_ids:
        _send_json(handler, 400, {"error": "ordered_ids is required"})
        return
    if repo.reorder_steps(flow_id, ordered_ids):
        _send_json(handler, 200, {"success": True})
    else:
        _send_json(handler, 500, {"error": "Failed to reorder steps"})


def handle_insert_step(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return
    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return
    data = _read_json_body(handler)
    after_step_id = data.get('after_step_id')
    err = _validate_step_data(data)
    if err:
        _send_json(handler, 400, {"error": err})
        return
    step = repo.insert_step_after(flow_id, after_step_id, data)
    if step:
        _send_json(handler, 201, step)
    else:
        _send_json(handler, 500, {"error": "Failed to insert step"})


def handle_flow_analytics(handler, flow_id: str):
    tenant_id = getattr(handler, 'tenant_id', None)
    if not tenant_id:
        _send_no_tenant_context(handler)
        return

    flow = repo.get_flow(tenant_id, flow_id)
    if not flow:
        _send_json(handler, 404, {"error": "Flow not found"})
        return

    today_count = repo.get_today_hype_count(tenant_id)
    total_count = repo.get_total_hype_count_for_flow(tenant_id, flow_id)

    _send_json(handler, 200, {
        "flow": flow,
        "today_message_count": today_count,
        "total_messages": total_count,
    })
