"""
Hype Chat service - AI-powered hype message generation and flow execution.
"""
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from core.logging import get_logger
from domains.hypechat import repo

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the voice of EntryLab's free Telegram channel. First person 'I' for trades, 'we' for the community. Never name yourself. Audience is beginners learning XAU/USD (gold).

THE FORMULA — every channel post needs all three:
1. BOLD RESULT — lead with the specific number. "+47 pips on the long". "Caught TP2 at 2661.20." Not "had a good trade today".
2. SHARE THE KEY — immediately explain the READ that made it work. Beginners want the HOW, not just the that.
3. CLEAN INVITE — close pointing toward VIP without shame, without urgency theater. (Skip on non-CTA messages.)

VOICE — QUIET CERTAINTY
- Calm, low-volume, restrained. Confidence is shown by NOT raising your voice.
- Periods, not exclamation marks. Almost zero "!" — reserve for genuine 1-in-100 moments.
- Drop cheerleader phrases: "let's go", "stay tuned", "let's keep the momentum", "ready to catch the next move".
- Drop trader cliches: "bulls in control", "smart money", "the trend is your friend".
- Sentence fragments fine. Real traders type fast.
- Bilingual touches OK — occasional Danish word ("nemlig", "sgu", "god nat") when it fits naturally.

SPECIFICITY
- Real prices, real session times, real macro drivers (DXY, yields, the print).
- Time-anchored: "London open in 40", "NY just took the high".
- Beginner-friendly: when you use a dense term (confluence, liquidity grab, the print, asymmetric setup), follow with a plain-English aside on first use.

VOCAB SIGNATURE
- The confluence (when macro and liquidity agree)
- Asymmetric setup (1:3+)
- The session handoff (Asia → London → NY)
- High-conviction / low-conviction days (sit out the latter and say so)
- The print (CPI / NFP releases)
- DXY rolling over / yields softening

NEVER
- No Lambos, watches, Dubai, "$X withdrawn", income screenshots, "financial freedom".
- No shaming the reader. No "while you were sleeping", "decide which side", "from the sidelines".
- No fake urgency. No "limited spots", no "price goes up tomorrow".
- No guaranteed returns. No "easy", "life-changing", "100% in 3 weeks".
- No all-caps lines. No motivational quotes. No hashtags.
- Never promise a fixed daily VIP plan time. Use generic "live entries fire in VIP" / "the room sees these in real time" instead.
- Emoji budget: 0-2 per message. ALLOWED only: 🟢 🔴 ☕ 🌙 🇩🇰 👉. Never rockets, money bags, fire, 100.
- Never name yourself.
- Don't mention losses on bad days.

LENGTH: 3-6 short lines. Telegram-native, not blog-post."""

DAY_MAP = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}

def is_active_today(active_days: str) -> bool:
    if not active_days or active_days.strip().lower() == 'daily':
        return True
    today = datetime.utcnow().weekday()
    raw = active_days.strip().lower()
    if '-' in raw and ',' not in raw:
        parts = raw.split('-')
        if len(parts) == 2 and parts[0] in DAY_MAP and parts[1] in DAY_MAP:
            start, end = DAY_MAP[parts[0]], DAY_MAP[parts[1]]
            if start <= end:
                return start <= today <= end
            return today >= start or today <= end
    days = [d.strip() for d in raw.split(',')]
    return any(DAY_MAP.get(d) == today for d in days)


def build_context(tenant_id: str, signal_context: str = None) -> str:
    from domains.crosspromo.repo import get_net_pips_over_days

    try:
        pips_today = get_net_pips_over_days(tenant_id, 1)
        pips_7d = get_net_pips_over_days(tenant_id, 7)

        context_parts = []
        if pips_today != 0:
            context_parts.append(f"Pips earned today: {pips_today:+.1f}")
        else:
            context_parts.append("No closed signals yet today")

        if pips_7d != 0:
            context_parts.append(f"Pips earned past 7 days: {pips_7d:+.1f}")
        else:
            context_parts.append("No closed signals in the past 7 days")

        if signal_context:
            context_parts.append("")
            context_parts.append(signal_context)

        return "\n".join(context_parts)
    except Exception as e:
        logger.warning(f"Error building context: {e}")
        return "Performance data currently unavailable"


def _get_arc_instruction(step: int, total: int) -> str:
    if total == 1:
        return "Write a single compelling message that references today's wins and ends with a call to action about joining VIP."
    if step == 1:
        return "This is the opening - set the tone, reference today's wins."
    elif step == total:
        return "This is the final message - end with a strong call to action about joining VIP."
    else:
        return "Build on what you said before, add a new angle or detail."


def _generate_messages_internal(tenant_id: str, custom_prompt: str, message_count: int = 3, signal_context: str = None, context_override: str = None) -> tuple:
    from openai import OpenAI

    try:
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or "https://api.openai.com/v1"

        if not api_key:
            logger.warning("OpenAI API key not configured (checked AI_INTEGRATIONS_OPENAI_API_KEY and OPENAI_API_KEY)")
            return [], "OpenAI API key not configured. Set OPENAI_API_KEY in your environment."

        client = OpenAI(api_key=api_key, base_url=base_url)
        if context_override is not None:
            context = context_override
        else:
            context = build_context(tenant_id, signal_context=signal_context)
        messages_result = []

        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

        for step in range(1, message_count + 1):
            arc_instruction = _get_arc_instruction(step, message_count)

            user_prompt = f"""Context about recent performance:
{context}

Instructions:
{custom_prompt}

You are writing a sequence of {message_count} messages. This is message {step} of {message_count}.
{arc_instruction}

Write ONLY the Telegram message, nothing else:"""

            conversation.append({"role": "user", "content": user_prompt})

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation,
                max_tokens=100,
            )

            message = response.choices[0].message.content.strip()

            if len(message) < 10 or len(message) > 2100:
                logger.warning(f"Generated message {step}/{message_count} length out of range: {len(message)}")
                message = ""

            messages_result.append(message)
            conversation.append({"role": "assistant", "content": message})

        logger.info(f"Generated sequence of {len(messages_result)} messages for tenant {tenant_id}")
        return messages_result, None

    except Exception as e:
        error_type = type(e).__name__
        error_detail = str(e)
        logger.exception(f"Error generating message sequence: [{error_type}] {error_detail}")
        return [], f"{error_type}: {error_detail}"


def generate_message_sequence(tenant_id: str, custom_prompt: str, message_count: int = 3, signal_context: str = None, context_override: str = None) -> List[str]:
    messages, error = _generate_messages_internal(tenant_id, custom_prompt, message_count, signal_context=signal_context, context_override=context_override)
    if error:
        logger.warning(f"generate_message_sequence failed for tenant {tenant_id}: {error}")
    return messages


def generate_message(tenant_id: str, custom_prompt: str, signal_context: str = None, context_override: str = None) -> str:
    result = generate_message_sequence(tenant_id, custom_prompt, 1, signal_context=signal_context, context_override=context_override)
    return result[0] if result else ""


def preview_message(tenant_id: str, custom_prompt: str, message_count: int = 3) -> Dict:
    context = build_context(tenant_id)
    messages, error = _generate_messages_internal(tenant_id, custom_prompt, message_count)

    result = {
        "messages": messages,
        "context": context,
    }

    if error:
        result["error"] = error

    return result


def send_hype_message(tenant_id: str, flow_id: str, step_number: int, custom_prompt: str, pre_generated_message: str = None) -> Dict:
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
    from integrations.telegram.client import send_message

    try:
        if pre_generated_message:
            message_text = pre_generated_message
        else:
            message_text = generate_message(tenant_id, custom_prompt)

        if not message_text:
            return {"success": False, "error": "Failed to generate message"}

        try:
            creds = get_bot_credentials(tenant_id, "signal_bot")
        except BotNotConfiguredError as e:
            logger.warning(f"Bot not configured for hype: {e}")
            return {"success": False, "error": str(e)}

        free_channel_id = creds.get("free_channel_id")
        if not free_channel_id:
            return {"success": False, "error": "Free channel not configured. Set it in Connections → Signal Bot."}

        bot_token = creds["bot_token"]

        def is_retryable_error(error_str: str) -> bool:
            """Check if an error is transient and retryable."""
            error_lower = error_str.lower()
            retryable_patterns = [
                "429", "500", "502", "503", "504",
                "too many requests", "retry after",
                "internal server error", "bad gateway",
                "gateway timeout", "service unavailable",
                "timeout", "connection", "network",
                "timed out", "temporarily unavailable",
            ]
            return any(pattern in error_lower for pattern in retryable_patterns)

        telegram_message_id = None
        result = None
        last_error = None
        max_attempts = 3
        base_wait = 2

        for attempt in range(1, max_attempts + 1):
            result = send_message(
                bot_token=bot_token,
                chat_id=free_channel_id,
                text=message_text,
                parse_mode="HTML",
            )

            if result.get("success"):
                if result.get("response") and result["response"].get("result"):
                    telegram_message_id = result["response"]["result"].get("message_id")
                logger.info(f"Message sent successfully on attempt {attempt}")
                break
            else:
                last_error = result.get("error", "Unknown error")
                if not is_retryable_error(last_error):
                    logger.warning(f"Non-retryable error on attempt {attempt}: {last_error}")
                    break
                
                if attempt < max_attempts:
                    wait_time = base_wait * (2 ** (attempt - 1))
                    logger.warning(f"Attempt {attempt} failed with retryable error: {last_error}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {max_attempts} attempts failed. Last error: {last_error}")

        repo.log_message(
            tenant_id=tenant_id,
            flow_id=flow_id,
            step_number=step_number,
            content_sent=None,
            telegram_message_id=telegram_message_id,
        )

        if result and result.get("success"):
            return {
                "success": True,
                "message_sent": message_text,
                "telegram_message_id": telegram_message_id,
            }
        else:
            return {
                "success": False,
                "error": last_error or "Failed to send message",
                "message_text_logged": True,
                "content_preserved": True,
            }

    except Exception as e:
        logger.exception(f"Error sending hype message: {e}")
        return {"success": False, "error": str(e)}


def _build_cta_message(cta_intro: str, cta_vip_label: str, cta_vip_url: str,
                        cta_support_label: str, cta_support_url: str) -> str:
    from urllib.parse import urlparse as _urlparse, urlencode, parse_qs, urlunparse
    cta_parts = []
    if cta_intro:
        cta_parts.append(cta_intro)
    links = []
    if cta_vip_label and cta_vip_url:
        parsed = _urlparse(cta_vip_url)
        existing_params = parse_qs(parsed.query)
        if not any(k.startswith('utm_') for k in existing_params):
            utm_params = {'utm_source': 'telegram', 'utm_medium': 'free_channel', 'utm_campaign': 'hype_bot'}
            new_query = (parsed.query + '&' if parsed.query else '') + urlencode(utm_params)
            cta_vip_url = urlunparse(parsed._replace(query=new_query))
        links.append(f'👉 <a href="{cta_vip_url}">{cta_vip_label}</a>')
    if cta_support_label and cta_support_url:
        links.append(f'🟢 <a href="{cta_support_url}">{cta_support_label}</a>')
    if links:
        cta_parts.append("\n\n".join(links))
    return "\n\n".join(cta_parts)


def _execute_flow_legacy(tenant_id: str, flow: dict, now: datetime, today_str: str,
                          custom_prompt: str, _visited: set) -> tuple:
    from domains.crosspromo.repo import enqueue_job
    scheduled = 0
    last_run_at = now

    message_count = flow.get("message_count", 3)
    interval_min = flow.get("interval_minutes", 90)
    interval_max = flow.get("interval_max_minutes", interval_min)
    if interval_max < interval_min:
        interval_max = interval_min
    delay_after_cta = flow.get("delay_after_cta_minutes", 10)
    flow_id = flow['id']

    bump_enabled = flow.get('bump_enabled', False)
    bump_preset = flow.get('bump_preset') or ''
    signal_context = None
    if bump_enabled and bump_preset:
        from db import get_bump_signal_context
        bump_msg_id, signal_context = get_bump_signal_context(tenant_id, bump_preset)
        if bump_msg_id:
            bump_delay = flow.get('bump_delay_minutes', 0) or 0
            bump_run_at = now + timedelta(minutes=bump_delay)
            bump_dedupe_key = f"hype_bump_{flow_id}_{today_str}"
            bump_job = enqueue_job(tenant_id=tenant_id, job_type='hype_bump',
                                   run_at=bump_run_at, payload={'preset': bump_preset},
                                   dedupe_key=bump_dedupe_key)
            if bump_job:
                scheduled += 1
                logger.info(f"[legacy] Scheduled bump preset={bump_preset} at {bump_run_at}")
        else:
            logger.info(f"[legacy] No bump message found for preset={bump_preset}")

    pre_generated_messages = generate_message_sequence(tenant_id, custom_prompt, message_count, signal_context=signal_context)
    cumulative_offset = delay_after_cta
    for step in range(1, message_count + 1):
        if step > 1:
            cumulative_offset += random.randint(interval_min, interval_max)
        run_at = now + timedelta(minutes=cumulative_offset)
        last_run_at = run_at
        payload = {"flow_id": flow_id, "step_number": step, "custom_prompt": custom_prompt, "job_sub_type": "hype_message"}
        if pre_generated_messages and step <= len(pre_generated_messages):
            payload["pre_generated_message"] = pre_generated_messages[step - 1]
        job = enqueue_job(tenant_id=tenant_id, job_type="hype_message", run_at=run_at,
                          payload=payload, dedupe_key=f"hype_{flow_id}_{today_str}_step{step}")
        if job:
            scheduled += 1
            logger.info(f"[legacy] Scheduled step {step} at {run_at}")

    if flow.get("cta_enabled"):
        cta_message = _build_cta_message(
            flow.get("cta_intro_text", ""), flow.get("cta_vip_label", ""),
            flow.get("cta_vip_url", ""), flow.get("cta_support_label", ""), flow.get("cta_support_url", ""))
        if cta_message.strip():
            cta_run_at = last_run_at + timedelta(minutes=flow.get("cta_delay_minutes", 30))
            cta_job = enqueue_job(tenant_id=tenant_id, job_type="hype_cta",
                                  run_at=cta_run_at,
                                  payload={"flow_id": flow_id, "cta_message": cta_message, "job_sub_type": "hype_cta"},
                                  dedupe_key=f"hype_{flow_id}_{today_str}_cta")
            if cta_job:
                scheduled += 1
                logger.info(f"[legacy] Scheduled CTA at {cta_run_at}")

    return scheduled, last_run_at


def execute_flow(tenant_id: str, flow_id: str, skip_day_check: bool = False,
                 base_time: datetime = None, _visited: set = None) -> Dict:
    from domains.crosspromo.repo import enqueue_job

    if _visited is None:
        _visited = set()
    if flow_id in _visited:
        logger.warning(f"Circular chain detected at flow {flow_id}, stopping")
        return {"success": False, "skipped": True, "messages_scheduled": 0}
    _visited.add(flow_id)

    try:
        today_count = repo.get_today_hype_count_for_flow(tenant_id, flow_id)
        if today_count > 0 and len(_visited) == 1:
            logger.info(f"Hype flow {flow_id} already triggered today for {tenant_id} ({today_count} messages)")
            return {"success": False, "error": "Flow already triggered today", "messages_scheduled": 0}

        flow = repo.get_flow(tenant_id, flow_id)
        if not flow:
            return {"success": False, "error": "Flow not found", "messages_scheduled": 0}

        if flow["status"] != "active":
            return {"success": False, "error": "Flow is not active", "messages_scheduled": 0}

        if not skip_day_check and not is_active_today(flow.get("active_days", "daily")):
            logger.info(f"Flow {flow_id} not active today (active_days={flow.get('active_days')})")
            return {"success": False, "error": "Flow not active today", "messages_scheduled": 0}

        now = base_time or datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        scheduled = 0
        last_run_at = now

        steps = repo.list_steps(flow_id)

        if not steps:
            custom_prompt = flow.get("custom_prompt", "")
            if not custom_prompt:
                return {"success": False, "error": "No prompt configured for flow", "messages_scheduled": 0}
            scheduled, last_run_at = _execute_flow_legacy(tenant_id, flow, now, today_str, custom_prompt, _visited)
            logger.info(f"[legacy] Flow {flow_id} executed with legacy path ({scheduled} jobs)")
        else:
            custom_prompt = flow.get("custom_prompt", "")

            signal_context = None
            has_reforward = any(s['step_type'] == 'reforward' for s in steps)
            has_ai_hype = any(s['step_type'] == 'ai_hype' for s in steps)
            if has_reforward or has_ai_hype:
                reforward_preset = next((s['reforward_preset'] for s in steps if s['step_type'] == 'reforward'), None)
                if not reforward_preset and flow.get('bump_enabled') and flow.get('bump_preset'):
                    reforward_preset = flow['bump_preset']
                if reforward_preset:
                    from db import get_bump_signal_context
                    _, signal_context = get_bump_signal_context(tenant_id, reforward_preset)

            ai_steps = [s for s in steps if s['step_type'] == 'ai_hype']
            ai_messages = []
            if ai_steps and custom_prompt:
                ai_messages = generate_message_sequence(tenant_id, custom_prompt, len(ai_steps), signal_context=signal_context)
                if not ai_messages:
                    logger.warning(f"Failed to pre-generate {len(ai_steps)} AI messages for flow {flow_id}")

            ai_idx = 0
            offset = 0
            step_num = 0

            for step in steps:
                offset += step['delay_minutes']
                run_at = now + timedelta(minutes=offset)
                last_run_at = run_at
                step_num += 1
                stype = step['step_type']

                if stype == 'reforward':
                    preset = step.get('reforward_preset')
                    if preset:
                        dedupe_key = f"hype_bump_{flow_id}_{today_str}_s{step_num}"
                        job = enqueue_job(tenant_id=tenant_id, job_type='hype_bump',
                                          run_at=run_at, payload={'preset': preset},
                                          dedupe_key=dedupe_key)
                        if job:
                            scheduled += 1
                            logger.info(f"Flow {flow_id} step {step_num}: reforward preset={preset} at {run_at}")

                elif stype == 'ai_hype':
                    text = ai_messages[ai_idx] if ai_idx < len(ai_messages) else None
                    ai_idx += 1
                    if text:
                        dedupe_key = f"hype_{flow_id}_{today_str}_s{step_num}"
                        payload = {"flow_id": flow_id, "step_number": step_num,
                                   "custom_prompt": custom_prompt, "job_sub_type": "hype_message",
                                   "pre_generated_message": text}
                        job = enqueue_job(tenant_id=tenant_id, job_type="hype_message",
                                          run_at=run_at, payload=payload, dedupe_key=dedupe_key)
                        if job:
                            scheduled += 1
                            logger.info(f"Flow {flow_id} step {step_num}: ai_hype at {run_at}")

                elif stype == 'message':
                    text = step.get('message_text', '').strip()
                    if text:
                        dedupe_key = f"hype_{flow_id}_{today_str}_s{step_num}"
                        payload = {"flow_id": flow_id, "step_number": step_num,
                                   "job_sub_type": "hype_message", "pre_generated_message": text}
                        job = enqueue_job(tenant_id=tenant_id, job_type="hype_message",
                                          run_at=run_at, payload=payload, dedupe_key=dedupe_key)
                        if job:
                            scheduled += 1
                            logger.info(f"Flow {flow_id} step {step_num}: message at {run_at}")

                elif stype == 'cta':
                    cta_message = _build_cta_message(
                        step.get('cta_intro_text', ''), step.get('cta_vip_label', ''),
                        step.get('cta_vip_url', ''), step.get('cta_support_label', ''),
                        step.get('cta_support_url', ''))
                    if cta_message.strip():
                        dedupe_key = f"hype_{flow_id}_{today_str}_cta_s{step_num}"
                        cta_payload = {"flow_id": flow_id, "cta_message": cta_message, "job_sub_type": "hype_cta"}
                        job = enqueue_job(tenant_id=tenant_id, job_type="hype_cta",
                                          run_at=run_at, payload=cta_payload, dedupe_key=dedupe_key)
                        if job:
                            scheduled += 1
                            logger.info(f"Flow {flow_id} step {step_num}: CTA at {run_at}")

        child_flows = [f for f in repo.get_active_flows(tenant_id)
                       if f.get('trigger_after_flow_id') == flow_id]
        for child in child_flows:
            child_delay = child.get('trigger_delay_minutes', 0) or 0
            child_base = last_run_at + timedelta(minutes=child_delay)
            child_result = execute_flow(
                tenant_id, child['id'],
                skip_day_check=False,
                base_time=child_base,
                _visited=set(_visited),
            )
            child_scheduled = child_result.get('messages_scheduled', 0)
            scheduled += child_scheduled
            logger.info(f"Chained child flow '{child.get('name')}' starting at {child_base} — {child_scheduled} jobs scheduled")

        return {"success": True, "messages_scheduled": scheduled}

    except Exception as e:
        logger.exception(f"Error executing flow: {e}")
        return {"success": False, "error": str(e), "messages_scheduled": 0}


def trigger_flow_from_cta(tenant_id: str) -> Dict:
    try:
        active_flows = repo.get_active_flows(tenant_id)
        if not active_flows:
            logger.info(f"No active hype flows for {tenant_id}")
            return {"success": False, "reason": "no_active_flows"}

        root_flows = [f for f in active_flows if not f.get('trigger_after_flow_id')]
        eligible_flows = [f for f in root_flows if is_active_today(f.get("active_days", "daily"))]
        skipped = len(root_flows) - len(eligible_flows)
        if skipped > 0:
            logger.info(f"Skipped {skipped} root flow(s) not active today")
        if not eligible_flows:
            logger.info(f"No root hype flows active today for {tenant_id}")
            return {"success": False, "reason": "no_flows_active_today"}

        results = []
        for flow in eligible_flows:
            root_delay = flow.get('trigger_delay_minutes', 0) or 0
            root_base = datetime.utcnow() + timedelta(minutes=root_delay)
            result = execute_flow(tenant_id, flow["id"], skip_day_check=True, base_time=root_base)
            results.append({"flow_id": flow["id"], "flow_name": flow["name"], **result})

        total_scheduled = sum(r.get("messages_scheduled", 0) for r in results)
        return {
            "success": total_scheduled > 0,
            "flows_triggered": len(results),
            "total_messages_scheduled": total_scheduled,
            "details": results,
        }

    except Exception as e:
        logger.exception(f"Error triggering flow from CTA: {e}")
        return {"success": False, "error": str(e)}
