"""
Journey engine - linear state machine for step execution.

Supports: message, question, delay step types.
V1 does NOT support conditional steps.
"""
import re
import time
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


class JourneyEngine:
    """
    Engine for executing journey steps.
    
    This is a linear state machine that processes steps in order.
    """
    
    def __init__(self):
        pass
    
    def _send_message(self, tenant_id: str, chat_id: int, text: str) -> bool:
        """Send a message via Telethon user client. No bot fallback."""
        try:
            from integrations.telegram.user_client import get_client
            uc = get_client(tenant_id)
            if not uc.is_connected():
                logger.error(f"Telethon not connected for tenant={tenant_id}, cannot send journey message")
                return False
            result = uc.send_message_sync(chat_id, text)
            if result.get('success'):
                return True
            logger.error(f"Telethon send failed for tenant={tenant_id}: {result.get('error')}")
            return False
        except Exception as e:
            logger.error(f"Telethon send error for tenant={tenant_id}: {e}")
            return False
    
    def start_journey_for_user(self, tenant_id: str, journey: Dict, 
                                telegram_chat_id: int, telegram_user_id: int,
                                first_name: str = '') -> Optional[Dict]:
        """
        Start a journey for a user, handling re-entry policy.
        
        Args:
            tenant_id: Tenant ID
            journey: Journey dict (must include id, re_entry_policy)
            telegram_chat_id: Telegram chat ID
            telegram_user_id: Telegram user ID
            
        Returns:
            New or existing session dict, or None on failure
        """
        from . import repo
        
        journey_id = journey['id']
        re_entry_policy = journey.get('re_entry_policy', 'block')
        
        existing_session = repo.get_active_session(tenant_id, journey_id, telegram_user_id)
        
        if existing_session:
            if re_entry_policy == 'block':
                logger.info(f"Blocked re-entry for user {telegram_user_id} in journey {journey_id} (silent, no message sent)")
                return existing_session
            
            elif re_entry_policy == 'restart':
                logger.info(f"Restarting session for user {telegram_user_id} in journey {journey_id}")
                repo.cancel_session(existing_session['id'])
            
            elif re_entry_policy == 'allow':
                logger.warning(f"re_entry_policy='allow' not fully supported yet, treating as restart")
                repo.cancel_session(existing_session['id'])
        
        first_step = repo.get_first_step(journey_id)
        if not first_step:
            logger.error(f"Journey {journey_id} has no steps")
            return None
        
        session = repo.create_session(
            tenant_id=tenant_id,
            journey_id=journey_id,
            telegram_chat_id=telegram_chat_id,
            telegram_user_id=telegram_user_id,
            first_step_id=first_step['id']
        )
        
        if session:
            logger.info(f"Started journey {journey_id} for user {telegram_user_id}, session {session['id']}")
            
            welcome_delay_seconds = journey.get('welcome_delay_seconds', 0) or 0
            welcome_message = journey.get('welcome_message', '')
            personalized_welcome = ''
            if welcome_message:
                personalized_welcome = welcome_message.replace('{first_name}', first_name or '').strip()
            
            # If no welcome message, delay is irrelevant - execute step 1 immediately
            if not welcome_message or not welcome_message.strip():
                self.execute_step(session, first_step, journey.get('bot_id'))
                return session
            
            if welcome_delay_seconds == 0:
                self._send_welcome_with_retry(tenant_id, telegram_chat_id, personalized_welcome)
                repo.mark_welcome_sent(session['id'])
                self.execute_step(session, first_step, journey.get('bot_id'))
            elif welcome_delay_seconds <= 60:
                self._defer_welcome_and_step(session, journey, first_step, first_name=first_name, delay_seconds=welcome_delay_seconds)
            else:
                repo.update_session_status(session['id'], 'waiting_delay')
                scheduled_for = datetime.utcnow() + timedelta(seconds=welcome_delay_seconds)
                repo.schedule_message(
                    tenant_id=tenant_id,
                    session_id=session['id'],
                    step_id=first_step['id'],
                    telegram_chat_id=telegram_chat_id,
                    message_content={
                        'type': 'welcome_and_step',
                        'welcome_text': personalized_welcome,
                        'step_type': first_step.get('step_type', 'message'),
                        'text': first_step.get('config', {}).get('text', ''),
                        'first_name': first_name
                    },
                    scheduled_for=scheduled_for
                )
                logger.info(f"Scheduled welcome+step1 for session {session['id']} in {welcome_delay_seconds}s via scheduler")
        
        return session
    
    def _send_welcome_with_retry(self, tenant_id: str, chat_id: int, text: str, max_attempts: int = 3) -> bool:
        """Send welcome message with exponential backoff retry."""
        backoff = [5, 15, 45]
        for attempt in range(1, max_attempts + 1):
            success = self._send_message(tenant_id, chat_id, text)
            if success:
                logger.info(f"Welcome message sent (attempt {attempt}) to chat {chat_id}")
                return True
            logger.warning(f"Welcome message attempt {attempt}/{max_attempts} failed for chat {chat_id}")
            if attempt < max_attempts:
                delay = backoff[attempt - 1] if attempt - 1 < len(backoff) else backoff[-1]
                time.sleep(delay)
        logger.error(f"Welcome message failed all {max_attempts} attempts for chat {chat_id}")
        return False
    
    def _defer_welcome_and_step(self, session: Dict, journey: Dict, step: Dict, 
                                  first_name: str = '', delay_seconds: int = 10):
        """Defer welcome message + first step by delay_seconds.
        Thread-based for delays <= 60s. For > 60s, caller should use scheduler instead."""
        from . import repo
        
        session_id = session['id']
        tenant_id = session['tenant_id']
        chat_id = session['telegram_chat_id']
        journey_id = journey['id']
        welcome_message = journey.get('welcome_message', '')
        bot_id = journey.get('bot_id')
        step_id = step['id']
        
        repo.update_session_status(session_id, 'waiting_delay')
        
        def _run():
            try:
                logger.info(f"Waiting {delay_seconds}s before welcome+step1 for session {session_id}")
                time.sleep(delay_seconds)
                
                fresh_session = repo.get_session_by_id(session_id)
                if not fresh_session:
                    logger.warning(f"Session {session_id} gone, skipping deferred welcome+step1")
                    return
                if fresh_session['status'] not in ('active', 'waiting_delay'):
                    logger.warning(f"Session {session_id} status={fresh_session['status']}, skipping")
                    return
                
                if fresh_session.get('welcome_sent_at'):
                    logger.info(f"Welcome already sent for session {session_id}, skipping to step 1")
                elif welcome_message:
                    personalized = welcome_message.replace('{first_name}', first_name or '').strip()
                    if personalized:
                        self._send_welcome_with_retry(tenant_id, chat_id, personalized)
                        repo.mark_welcome_sent(session_id)
                
                repo.update_session_status(session_id, 'active')
                fresh_session = repo.get_session_by_id(session_id)
                if fresh_session:
                    self.execute_step(fresh_session, step, bot_id)
                
            except Exception as e:
                logger.exception(f"Error in deferred welcome+step1 for session {session_id}: {e}")

        t = threading.Thread(target=_run, daemon=True, name=f"welcome-delay-{session_id}")
        t.start()
        logger.info(f"Deferred welcome+step1 by {delay_seconds}s (thread={t.name})")

    def execute_step(self, session: Dict, step: Dict, bot_id: str = None) -> bool:
        """
        Execute a single step.
        
        Args:
            session: Session dict
            step: Step dict
            bot_id: Bot ID for sending messages
            
        Returns:
            True if step was executed (or queued), False on failure
        """
        from . import repo
        
        step_type = step['step_type']
        config = step.get('config', {})
        
        logger.info(f"Executing step {step['id']} (type={step_type}) for session {session['id']}")
        
        if step_type == 'message':
            return self._execute_message_step(session, step, config, bot_id)
        
        elif step_type == 'question':
            return self._execute_question_step(session, step, config, bot_id)
        
        elif step_type == 'delay':
            return self._execute_delay_step(session, step, config, bot_id)
        
        elif step_type == 'wait_for_reply':
            return self._execute_wait_for_reply_step(session, step, config, bot_id)
        
        elif step_type == 'conditional':
            logger.warning(f"Conditional steps not supported in V1, skipping step {step['id']}")
            return self._advance_to_next_step(session, step, bot_id)
        
        else:
            logger.error(f"Unknown step type: {step_type}")
            return False
    
    def _wrap_urls(self, text: str, tenant_id: str, journey_id: str, step_id: str) -> str:
        from . import repo
        url_pattern = re.compile(r'(https?://[^\s<>"\']+)')
        def replace_url(match):
            url = match.group(1)
            try:
                return repo.create_tracked_link(tenant_id, journey_id, step_id, url)
            except Exception as e:
                logger.warning(f"Failed to wrap URL {url}: {e}")
                return url
        return url_pattern.sub(replace_url, text)

    def _defer_step_to_scheduler(self, session: Dict, step: Dict, text: str, step_type: str) -> bool:
        """Defer a step execution to the scheduler instead of blocking the thread."""
        from . import repo
        delay = step.get('config', {}).get('delay_seconds', 0)
        capped_delay = min(delay, 3600)
        scheduled_for = datetime.utcnow() + timedelta(seconds=capped_delay)

        if text:
            text = self._wrap_urls(text, session['tenant_id'], session['journey_id'], step['id'])

        message_content = {
            'text': text or '',
            'step_type': step_type
        }
        message_id = repo.schedule_message(
            tenant_id=session['tenant_id'],
            session_id=session['id'],
            step_id=step['id'],
            telegram_chat_id=session['telegram_chat_id'],
            message_content=message_content,
            scheduled_for=scheduled_for
        )
        if message_id:
            repo.update_session_status(session['id'], 'waiting_delay')
            logger.info(f"Deferred {step_type} step {step['id']} to scheduler ({capped_delay}s)")
            return True
        logger.error(f"Failed to defer {step_type} step {step['id']}")
        return False

    def _execute_message_step(self, session: Dict, step: Dict, config: Dict, bot_id: str) -> bool:
        """Execute a message step - send immediately and advance."""
        text = config.get('content') or config.get('text', '')
        
        delay = config.get('delay_seconds', 0)
        if delay and delay > 15:
            return self._defer_step_to_scheduler(session, step, text, 'message')
        elif delay and delay > 0:
            logger.info(f"Short delay {delay}s before message step {step['id']}")
            time.sleep(delay)
        
        if not text:
            logger.warning(f"Message step {step['id']} has no text")
            return self._advance_to_next_step(session, step, bot_id)
        
        text = self._wrap_urls(text, session['tenant_id'], session['journey_id'], step['id'])
        success = self._send_message(session['tenant_id'], session['telegram_chat_id'], text)
        if not success:
            logger.error(f"Failed to send message for step {step['id']}")
            return False
        
        from . import repo
        repo.increment_step_send(session['tenant_id'], session['journey_id'], step['id'], session['telegram_user_id'])
        
        return self._advance_to_next_step(session, step, bot_id)
    
    def _execute_question_step(self, session: Dict, step: Dict, config: Dict, bot_id: str) -> bool:
        """Execute a question step - send question and wait for reply."""
        text = config.get('content') or config.get('text', '')
        
        delay = config.get('delay_seconds', 0)
        if delay and delay > 15:
            return self._defer_step_to_scheduler(session, step, text, 'question')
        elif delay and delay > 0:
            logger.info(f"Short delay {delay}s before question step {step['id']}")
            time.sleep(delay)
        
        if not text:
            logger.warning(f"Question step {step['id']} has no text")
            return self._advance_to_next_step(session, step, bot_id)
        
        text = self._wrap_urls(text, session['tenant_id'], session['journey_id'], step['id'])
        success = self._send_message(session['tenant_id'], session['telegram_chat_id'], text)
        if not success:
            logger.error(f"Failed to send question for step {step['id']}")
            return False
        
        from . import repo
        repo.increment_step_send(session['tenant_id'], session['journey_id'], step['id'], session['telegram_user_id'])
        
        return True
    
    def _execute_delay_step(self, session: Dict, step: Dict, config: Dict, bot_id: str) -> bool:
        """Execute a delay step - schedule next step for later."""
        from . import repo
        
        min_minutes = config.get('min_minutes', 60)
        max_minutes = config.get('max_minutes', 120)
        
        delay_minutes = random.randint(min_minutes, max_minutes)
        scheduled_for = datetime.utcnow() + timedelta(minutes=delay_minutes)
        
        next_step = repo.get_next_step(session['journey_id'], step['step_order'])
        
        if not next_step:
            logger.info(f"Delay step {step['id']} is last step, completing journey")
            repo.update_session_status(session['id'], 'completed')
            return True
        
        next_step_config = next_step.get('config', {})
        message_content = {
            'text': next_step_config.get('content') or next_step_config.get('text', ''),
            'step_type': next_step['step_type']
        }
        
        message_id = repo.schedule_message(
            tenant_id=session['tenant_id'],
            session_id=session['id'],
            step_id=next_step['id'],
            telegram_chat_id=session['telegram_chat_id'],
            message_content=message_content,
            scheduled_for=scheduled_for
        )
        
        if message_id:
            repo.update_session_status(session['id'], 'waiting_delay')
            logger.info(f"Scheduled message {message_id} for {scheduled_for} ({delay_minutes} min delay)")
            return True
        else:
            logger.error(f"Failed to schedule delayed message for step {step['id']}")
            return False
    
    def _execute_wait_for_reply_step(self, session: Dict, step: Dict, config: Dict, bot_id: str) -> bool:
        """
        Execute a wait_for_reply step - pause journey until user replies.
        
        Optionally sends a prompt message and sets a timeout.
        Config options:
            - content/text: Optional message to send before waiting
            - timeout_minutes: Minutes to wait before auto-advancing (0 = no timeout)
        """
        from . import repo
        
        text = config.get('content') or config.get('text', '')
        timeout_minutes = config.get('timeout_minutes', 0)
        
        delay = config.get('delay_seconds', 0)
        if delay and delay > 15:
            return self._defer_step_to_scheduler(session, step, text, 'wait_for_reply')
        elif delay and delay > 0:
            logger.info(f"Short delay {delay}s before wait_for_reply step {step['id']}")
            time.sleep(delay)
        
        if text:
            text = self._wrap_urls(text, session['tenant_id'], session['journey_id'], step['id'])
            success = self._send_message(session['tenant_id'], session['telegram_chat_id'], text)
            if not success:
                logger.error(f"Failed to send wait_for_reply prompt for step {step['id']}")
            else:
                repo.increment_step_send(session['tenant_id'], session['journey_id'], step['id'], session['telegram_user_id'])
        
        repo.set_session_awaiting_reply(
            session_id=session['id'],
            step_id=step['id'],
            timeout_minutes=timeout_minutes if timeout_minutes > 0 else None
        )
        
        logger.info(f"Session {session['id']} now waiting for reply (timeout={timeout_minutes}min)")
        return True
    
    def handle_wait_for_reply_response(self, session: Dict, message_text: str, bot_id: str = None) -> bool:
        """
        Handle a user's reply to a wait_for_reply step.
        
        Stores the reply and sets reply_received_at. The scheduler will check
        at the timeout whether a reply was received and act accordingly.
        This does NOT immediately advance - we wait for the full wait period.
        """
        from . import repo
        
        if not session.get('current_step_id'):
            logger.warning(f"Session {session['id']} has no current step")
            return False
        
        current_step = repo.get_step_by_id(session['current_step_id'])
        if not current_step:
            logger.error(f"Step {session['current_step_id']} not found")
            return False
        
        if current_step['step_type'] != 'wait_for_reply':
            logger.debug(f"Current step is not wait_for_reply, ignoring")
            return False
        
        repo.store_user_reply(session['id'], message_text)
        
        config = current_step.get('config', {})
        branch_keyword = config.get('branch_keyword', '')

        if branch_keyword:
            if branch_keyword.lower() in message_text.lower():
                target_step_id = config.get('branch_true_step_id')
                logger.info(f"Branch match: '{branch_keyword}' found, jumping to step {target_step_id}")
            else:
                target_step_id = config.get('branch_false_step_id')
                logger.info(f"Branch no match: '{branch_keyword}' not found, jumping to step {target_step_id}")
            
            if target_step_id:
                target_step = repo.get_step_by_id(target_step_id)
                if target_step:
                    repo.update_session_status(session['id'], 'active')
                    repo.update_session_current_step(session['id'], target_step_id)
                    updated_session = repo.get_session_by_id(session['id'])
                    if updated_session:
                        return self.execute_step(updated_session, target_step, bot_id)
            
            repo.update_session_status(session['id'], 'active')
            return self._advance_to_next_step(session, current_step, bot_id)
        else:
            repo.update_session_status(session['id'], 'active')
            return self._advance_to_next_step(session, current_step, bot_id)
    
    def timeout_wait_for_reply(self, session: Dict, step: Dict, bot_id: str = None) -> bool:
        """
        Handle timeout for a wait_for_reply step.
        
        Called by scheduler when wait_timeout_at has passed.
        Checks if reply was received within the wait window:
        - If reply_received_at is set: Continue to next step (success)
        - If no reply: Execute timeout_action (continue or end journey)
        """
        from . import repo
        
        config = step.get('config', {})
        timeout_action = config.get('timeout_action', 'continue')
        timeout_message = config.get('timeout_message', '')
        
        reply_received = session.get('reply_received_at') is not None
        
        if reply_received:
            logger.info(f"Wait complete for session {session['id']} - reply received, advancing")
            repo.update_session_status(session['id'], 'active')
            repo.clear_reply_received(session['id'])
            return self._advance_to_next_step(session, step, bot_id)
        else:
            logger.info(f"Wait complete for session {session['id']} - no reply, timeout_action={timeout_action}")
            
            if timeout_message:
                self._send_message(session['tenant_id'], session['telegram_chat_id'], timeout_message)
            
            if timeout_action == 'end':
                repo.update_session_status(session['id'], 'completed')
                logger.info(f"Journey ended due to no reply for session {session['id']}")
                return True
            else:
                repo.update_session_status(session['id'], 'active')
                repo.clear_reply_received(session['id'])
                return self._advance_to_next_step(session, step, bot_id)
    
    def _advance_to_next_step(self, session: Dict, current_step: Dict, bot_id: str) -> bool:
        """Advance to the next step in the journey."""
        from . import repo
        
        next_step = repo.get_next_step(session['journey_id'], current_step['step_order'])
        
        if not next_step:
            logger.info(f"Journey complete for session {session['id']}")
            repo.update_session_status(session['id'], 'completed')
            return True
        
        repo.update_session_current_step(session['id'], next_step['id'])
        
        updated_session = repo.get_session_by_id(session['id'])
        if updated_session:
            return self.execute_step(updated_session, next_step, bot_id)
        
        return False
    
    def handle_user_reply(self, session: Dict, message_text: str, bot_id: str = None) -> bool:
        """
        Handle a user's reply to a question step.
        
        Args:
            session: Active session dict
            message_text: User's reply text
            bot_id: Bot ID for responses
            
        Returns:
            True if reply was processed, False otherwise
        """
        from . import repo
        
        if not session.get('current_step_id'):
            logger.warning(f"Session {session['id']} has no current step")
            return False
        
        current_step = repo.get_step_by_id(session['current_step_id'])
        if not current_step:
            logger.error(f"Step {session['current_step_id']} not found")
            return False
        
        if current_step['step_type'] != 'question':
            logger.debug(f"Current step is not a question, ignoring reply")
            return False
        
        config = current_step.get('config', {})
        answer_key = config.get('answer_key', 'answer')
        validation = config.get('validation', 'text')
        
        validated_value = self._validate_answer(message_text, validation)
        
        if validated_value is None:
            error_msg = self._get_validation_error_message(validation)
            if error_msg:
                self._send_message(session['tenant_id'], session['telegram_chat_id'], error_msg)
            return False
        
        repo.store_answer(session['id'], answer_key, validated_value)
        logger.info(f"Stored answer '{answer_key}' = '{validated_value}' for session {session['id']}")
        
        updated_session = repo.get_session_by_id(session['id'])
        if updated_session:
            return self._advance_to_next_step(updated_session, current_step, bot_id)
        
        return False
    
    def _validate_answer(self, text: str, validation: str) -> Any:
        """
        Validate and convert an answer based on validation type.
        
        Returns:
            Converted value if valid, None if invalid
        """
        text = text.strip()
        
        if not text:
            return None
        
        if validation == 'text':
            return text
        
        elif validation == 'number':
            try:
                text_clean = text.replace(',', '').replace(' ', '')
                if '.' in text_clean:
                    return float(text_clean)
                return int(text_clean)
            except ValueError:
                return None
        
        elif validation == 'money':
            try:
                text_clean = text.replace('$', '').replace('€', '').replace('£', '')
                text_clean = text_clean.replace(',', '').replace(' ', '')
                return float(text_clean)
            except ValueError:
                return None
        
        elif validation == 'country':
            if len(text) == 2 and text.isalpha():
                return text.upper()
            return text
        
        else:
            return text
    
    def _get_validation_error_message(self, validation: str) -> Optional[str]:
        """Get an error message for a validation failure."""
        messages = {
            'number': "Please enter a valid number.",
            'money': "Please enter a valid amount (e.g., 500 or $500).",
            'country': "Please enter a valid country name or code."
        }
        return messages.get(validation)
    
    def resume_after_delay(self, session: Dict, step: Dict, bot_id: str = None) -> bool:
        """
        Resume a session after a delay step completes.
        
        Called by the scheduler when a delayed message is sent.
        """
        from . import repo
        
        repo.update_session_status(session['id'], 'active')
        repo.update_session_current_step(session['id'], step['id'])
        
        updated_session = repo.get_session_by_id(session['id'])
        if updated_session:
            return self.execute_step(updated_session, step, bot_id)
        
        return False
