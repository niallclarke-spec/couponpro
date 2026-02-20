"""
Hype Chat service - AI-powered hype message generation and flow execution.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict

from core.logging import get_logger
from domains.hypechat import repo

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the owner of a premium forex gold signals Telegram channel called EntryLab. You run a VIP signals service that consistently delivers winning XAU/USD trades. You're confident, authentic, and results-driven. You never use hashtags. You write short, punchy Telegram messages with 2-3 emojis max. Keep messages under 280 characters."""


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


def generate_message(tenant_id: str, custom_prompt: str) -> str:
    from openai import OpenAI

    try:
        api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

        if not api_key or not base_url:
            logger.warning("OpenAI credentials not configured")
            return ""

        client = OpenAI(api_key=api_key, base_url=base_url)

        context = build_context(tenant_id)

        user_prompt = f"""Context about recent performance:
{context}

Instructions:
{custom_prompt}

Write ONLY the Telegram message, nothing else:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
        )

        message = response.choices[0].message.content.strip()

        if len(message) < 10 or len(message) > 500:
            logger.warning(f"Generated message length out of range: {len(message)}")
            return ""

        return message

    except Exception as e:
        logger.exception(f"Error generating hype message: {e}")
        return ""


def preview_message(tenant_id: str, custom_prompt: str) -> Dict:
    context = build_context(tenant_id)
    message = generate_message(tenant_id, custom_prompt)

    return {
        "message": message,
        "context": context,
    }


def send_hype_message(tenant_id: str, flow_id: str, step_number: int, custom_prompt: str) -> Dict:
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
    from integrations.telegram.client import send_message
    from domains.crosspromo.repo import get_settings

    try:
        message_text = generate_message(tenant_id, custom_prompt)
        if not message_text:
            return {"success": False, "error": "Failed to generate message"}

        try:
            creds = get_bot_credentials(tenant_id, "signal_bot")
        except BotNotConfiguredError as e:
            logger.warning(f"Bot not configured for hype: {e}")
            return {"success": False, "error": str(e)}

        settings = get_settings(tenant_id)
        if not settings or not settings.get("free_channel_id"):
            return {"success": False, "error": "Free channel not configured in crosspromo settings"}

        free_channel_id = settings["free_channel_id"]
        bot_token = creds["bot_token"]

        result = send_message(
            bot_token=bot_token,
            chat_id=free_channel_id,
            text=message_text,
            parse_mode="HTML",
        )

        telegram_message_id = None
        if result.get("ok") and result.get("result"):
            telegram_message_id = result["result"].get("message_id")

        repo.log_message(
            tenant_id=tenant_id,
            flow_id=flow_id,
            step_number=step_number,
            content_sent=message_text,
            telegram_message_id=telegram_message_id,
        )

        return {
            "success": True,
            "message_sent": message_text,
            "telegram_message_id": telegram_message_id,
        }

    except Exception as e:
        logger.exception(f"Error sending hype message: {e}")
        return {"success": False, "error": str(e)}


def execute_flow(tenant_id: str, flow_id: str) -> Dict:
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

        custom_prompt = flow.get("custom_prompt", "")
        if not custom_prompt:
            return {"success": False, "error": "No prompt configured for flow", "messages_scheduled": 0}

        message_count = flow.get("message_count", 3)
        interval_minutes = flow.get("interval_minutes", 90)
        delay_after_cta = flow.get("delay_after_cta_minutes", 10)

        now = datetime.utcnow()
        scheduled = 0

        for step in range(1, message_count + 1):
            offset_minutes = delay_after_cta + ((step - 1) * interval_minutes)
            run_at = now + timedelta(minutes=offset_minutes)

            today_str = now.strftime("%Y-%m-%d")
            dedupe_key = f"hype_{flow_id}_{today_str}_step{step}"

            payload = {
                "flow_id": flow_id,
                "step_number": step,
                "custom_prompt": custom_prompt,
                "job_sub_type": "hype_message",
            }

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

        results = []
        for flow in active_flows:
            result = execute_flow(tenant_id, flow["id"])
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
