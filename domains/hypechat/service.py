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

SYSTEM_PROMPT = """You are the owner of a premium forex gold signals Telegram channel called EntryLab. You run a VIP signals service that consistently delivers winning XAU/USD trades. You're confident, authentic, and results-driven. You never use hashtags. You write short, punchy Telegram messages with 2-3 emojis max."""

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


def build_context(tenant_id: str) -> str:
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


def _generate_messages_internal(tenant_id: str, custom_prompt: str, message_count: int = 3) -> tuple:
    from openai import OpenAI

    try:
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL") or "https://api.openai.com/v1"

        if not api_key:
            logger.warning("OpenAI API key not configured (checked AI_INTEGRATIONS_OPENAI_API_KEY and OPENAI_API_KEY)")
            return [], "OpenAI API key not configured. Set OPENAI_API_KEY in your environment."

        client = OpenAI(api_key=api_key, base_url=base_url)
        context = build_context(tenant_id)
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


def generate_message_sequence(tenant_id: str, custom_prompt: str, message_count: int = 3) -> List[str]:
    messages, error = _generate_messages_internal(tenant_id, custom_prompt, message_count)
    if error:
        logger.warning(f"generate_message_sequence failed for tenant {tenant_id}: {error}")
    return messages


def generate_message(tenant_id: str, custom_prompt: str) -> str:
    result = generate_message_sequence(tenant_id, custom_prompt, 1)
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
            content_sent=message_text,
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


def execute_flow(tenant_id: str, flow_id: str, skip_day_check: bool = False) -> Dict:
    from domains.crosspromo.repo import enqueue_job

    try:
        today_count = repo.get_today_hype_count(tenant_id)
        if today_count > 0:
            logger.info(f"Hype already triggered today for {tenant_id} ({today_count} messages)")
            return {"success": False, "error": "Hype already triggered today", "messages_scheduled": 0}

        flow = repo.get_flow(tenant_id, flow_id)
        if not flow:
            return {"success": False, "error": "Flow not found", "messages_scheduled": 0}

        if flow["status"] != "active":
            return {"success": False, "error": "Flow is not active", "messages_scheduled": 0}

        if not skip_day_check and not is_active_today(flow.get("active_days", "daily")):
            logger.info(f"Flow {flow_id} not active today (active_days={flow.get('active_days')})")
            return {"success": False, "error": "Flow not active today", "messages_scheduled": 0}

        custom_prompt = flow.get("custom_prompt", "")
        if not custom_prompt:
            return {"success": False, "error": "No prompt configured for flow", "messages_scheduled": 0}

        message_count = flow.get("message_count", 3)
        interval_min = flow.get("interval_minutes", 90)
        interval_max = flow.get("interval_max_minutes", interval_min)
        if interval_max < interval_min:
            interval_max = interval_min
        delay_after_cta = flow.get("delay_after_cta_minutes", 10)

        pre_generated_messages = generate_message_sequence(tenant_id, custom_prompt, message_count)
        if not pre_generated_messages:
            logger.warning(f"Failed to pre-generate messages for flow {flow_id}, will fallback to per-job generation")

        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        scheduled = 0
        cumulative_offset = delay_after_cta
        last_run_at = now + timedelta(minutes=cumulative_offset)

        for step in range(1, message_count + 1):
            if step > 1:
                cumulative_offset += random.randint(interval_min, interval_max)
            run_at = now + timedelta(minutes=cumulative_offset)
            last_run_at = run_at

            dedupe_key = f"hype_{flow_id}_{today_str}_step{step}"

            payload = {
                "flow_id": flow_id,
                "step_number": step,
                "custom_prompt": custom_prompt,
                "job_sub_type": "hype_message",
            }

            if pre_generated_messages and step <= len(pre_generated_messages):
                payload["pre_generated_message"] = pre_generated_messages[step - 1]

            job = enqueue_job(
                tenant_id=tenant_id,
                job_type="hype_message",
                run_at=run_at,
                payload=payload,
                dedupe_key=dedupe_key,
            )

            if job:
                scheduled += 1
                logger.info(f"Scheduled hype step {step} at {run_at} for flow {flow_id}")

        cta_enabled = flow.get("cta_enabled", False)
        if cta_enabled:
            cta_intro = flow.get("cta_intro_text", "")
            cta_vip_label = flow.get("cta_vip_label", "")
            cta_vip_url = flow.get("cta_vip_url", "")
            cta_support_label = flow.get("cta_support_label", "")
            cta_support_url = flow.get("cta_support_url", "")
            cta_delay = flow.get("cta_delay_minutes", 30)

            cta_parts = []
            if cta_intro:
                cta_parts.append(cta_intro)

            links = []
            if cta_vip_label and cta_vip_url:
                from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
                parsed = urlparse(cta_vip_url)
                existing_params = parse_qs(parsed.query)
                if not any(k.startswith('utm_') for k in existing_params):
                    utm_params = {
                        'utm_source': 'telegram',
                        'utm_medium': 'free_channel',
                        'utm_campaign': 'hype_bot'
                    }
                    separator = '&' if parsed.query else ''
                    new_query = parsed.query + separator + urlencode(utm_params) if parsed.query else urlencode(utm_params)
                    cta_vip_url = urlunparse(parsed._replace(query=new_query))
                links.append(f'👉 <a href="{cta_vip_url}">{cta_vip_label}</a>')
            if cta_support_label and cta_support_url:
                links.append(f'🟢 <a href="{cta_support_url}">{cta_support_label}</a>')

            if links:
                cta_parts.append("\n".join(links))

            cta_message = "\n\n".join(cta_parts)

            if cta_message.strip():
                cta_run_at = last_run_at + timedelta(minutes=cta_delay)
                cta_dedupe_key = f"hype_{flow_id}_{today_str}_cta"

                cta_payload = {
                    "flow_id": flow_id,
                    "cta_message": cta_message,
                    "job_sub_type": "hype_cta",
                }

                cta_job = enqueue_job(
                    tenant_id=tenant_id,
                    job_type="hype_cta",
                    run_at=cta_run_at,
                    payload=cta_payload,
                    dedupe_key=cta_dedupe_key,
                )

                if cta_job:
                    scheduled += 1
                    logger.info(f"Scheduled CTA at {cta_run_at} for flow {flow_id}")

        return {"success": True, "messages_scheduled": scheduled}

    except Exception as e:
        logger.exception(f"Error executing flow: {e}")
        return {"success": False, "error": str(e), "messages_scheduled": 0}


def trigger_flow_from_cta(tenant_id: str) -> Dict:
    try:
        today_count = repo.get_today_hype_count(tenant_id)
        if today_count > 0:
            logger.info(f"Hype already triggered today for {tenant_id}, skipping CTA trigger")
            return {"success": False, "reason": "already_triggered_today"}

        active_flows = repo.get_active_flows(tenant_id)
        if not active_flows:
            logger.info(f"No active hype flows for {tenant_id}")
            return {"success": False, "reason": "no_active_flows"}

        eligible_flows = [f for f in active_flows if is_active_today(f.get("active_days", "daily"))]
        skipped = len(active_flows) - len(eligible_flows)
        if skipped > 0:
            logger.info(f"Skipped {skipped} flow(s) not active today")
        if not eligible_flows:
            logger.info(f"No hype flows active today for {tenant_id}")
            return {"success": False, "reason": "no_flows_active_today"}

        results = []
        for flow in eligible_flows:
            result = execute_flow(tenant_id, flow["id"], skip_day_check=True)
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
