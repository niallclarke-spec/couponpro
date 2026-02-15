import os
import threading
from typing import Optional, Dict, Any

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
)

from core.logging import get_logger
from integrations.telegram.user_client import (
    SESSION_BASE_DIR,
    get_client,
    _run_in_bg,
)
from integrations.telegram.user_session import save_session

logger = get_logger('telethon_auth')

_auth_states: Dict[str, Dict[str, Any]] = {}
_auth_lock = threading.Lock()


def _set_auth_state(tenant_id: str, state: Dict[str, Any]):
    with _auth_lock:
        _auth_states[tenant_id] = state


def _get_auth_state(tenant_id: str) -> Optional[Dict[str, Any]]:
    with _auth_lock:
        return _auth_states.get(tenant_id)


def _clear_auth_state(tenant_id: str):
    with _auth_lock:
        _auth_states.pop(tenant_id, None)


async def _send_verification_code(tenant_id: str, api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
    os.makedirs(SESSION_BASE_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_BASE_DIR, tenant_id)

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    masked_phone = '***' + phone[-4:] if len(phone) >= 4 else '***'
    logger.info(f"Sending verification code for tenant={tenant_id}, phone={masked_phone}")

    try:
        result = await client.send_code_request(phone)
        _set_auth_state(tenant_id, {
            'client': client,
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'api_id': api_id,
            'api_hash': api_hash,
            'status': 'code_sent',
        })
        logger.info(f"Verification code sent for tenant={tenant_id}")
        return {
            'success': True,
            'phone_code_hash': result.phone_code_hash,
            'status': 'code_sent',
        }
    except Exception as e:
        await client.disconnect()
        logger.exception(f"Failed to send verification code for tenant={tenant_id}: {e}")
        return {'success': False, 'error': str(e)}


def send_verification_code(tenant_id: str, api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
    return _run_in_bg(_send_verification_code(tenant_id, api_id, api_hash, phone))


async def _verify_code(tenant_id: str, code: str, phone_code_hash: str) -> Dict[str, Any]:
    state = _get_auth_state(tenant_id)
    if not state or state.get('status') != 'code_sent':
        return {'success': False, 'error': 'No pending verification. Send code first.'}

    client: TelegramClient = state['client']
    phone = state['phone']

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)

        save_session(tenant_id)

        uc = get_client(tenant_id)
        uc._api_id = state['api_id']
        uc._api_hash = state['api_hash']
        uc._phone = phone

        await client.disconnect()
        _clear_auth_state(tenant_id)

        logger.info(f"Verification successful for tenant={tenant_id}")
        return {'success': True, 'status': 'authorized'}

    except SessionPasswordNeededError:
        _set_auth_state(tenant_id, {**state, 'status': '2fa_required'})
        logger.info(f"2FA required for tenant={tenant_id}")
        return {'success': True, 'status': '2fa_required'}

    except PhoneCodeInvalidError:
        logger.warning(f"Invalid code for tenant={tenant_id}")
        return {'success': False, 'error': 'Invalid verification code'}

    except PhoneCodeExpiredError:
        _clear_auth_state(tenant_id)
        await client.disconnect()
        logger.warning(f"Expired code for tenant={tenant_id}")
        return {'success': False, 'error': 'Verification code expired. Please request a new one.'}

    except Exception as e:
        logger.exception(f"Verification failed for tenant={tenant_id}: {e}")
        return {'success': False, 'error': str(e)}


def verify_code(tenant_id: str, code: str, phone_code_hash: str) -> Dict[str, Any]:
    return _run_in_bg(_verify_code(tenant_id, code, phone_code_hash))


async def _verify_2fa(tenant_id: str, password: str) -> Dict[str, Any]:
    state = _get_auth_state(tenant_id)
    if not state or state.get('status') != '2fa_required':
        return {'success': False, 'error': 'No pending 2FA verification.'}

    client: TelegramClient = state['client']

    try:
        await client.sign_in(password=password)

        save_session(tenant_id)

        uc = get_client(tenant_id)
        uc._api_id = state['api_id']
        uc._api_hash = state['api_hash']
        uc._phone = state['phone']

        await client.disconnect()
        _clear_auth_state(tenant_id)

        logger.info(f"2FA verification successful for tenant={tenant_id}")
        return {'success': True, 'status': 'authorized'}

    except PasswordHashInvalidError:
        logger.warning(f"Invalid 2FA password for tenant={tenant_id}")
        return {'success': False, 'error': 'Invalid 2FA password'}

    except Exception as e:
        logger.exception(f"2FA verification failed for tenant={tenant_id}: {e}")
        return {'success': False, 'error': str(e)}


def verify_2fa(tenant_id: str, password: str) -> Dict[str, Any]:
    return _run_in_bg(_verify_2fa(tenant_id, password))
