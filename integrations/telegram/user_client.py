import os
import time
import asyncio
import threading
from datetime import datetime, date
from typing import Optional, Dict, Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError

from core.logging import get_logger

logger = get_logger('telethon_client')

SESSION_BASE_DIR = os.environ.get('TELETHON_SESSION_DIR', '/tmp/telethon_sessions')

_clients: Dict[str, 'TelethonUserClient'] = {}
_clients_lock = threading.Lock()

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()


def _ensure_bg_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is not None and _bg_loop.is_running():
            return _bg_loop

        _bg_loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(_bg_loop)
            _bg_loop.run_forever()

        _bg_thread = threading.Thread(target=_run, daemon=True, name='telethon-loop')
        _bg_thread.start()
        return _bg_loop


def _run_in_bg(coro):
    loop = _ensure_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


def get_client(tenant_id: str) -> 'TelethonUserClient':
    with _clients_lock:
        if tenant_id in _clients:
            return _clients[tenant_id]
        client = TelethonUserClient(tenant_id)
        _clients[tenant_id] = client
        return client


def remove_client(tenant_id: str):
    with _clients_lock:
        _clients.pop(tenant_id, None)


class RateLimitState:
    def __init__(self, max_per_minute=20, max_per_hour=200, max_per_day=500):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self._lock = threading.Lock()
        self._minute_sends: list = []
        self._hour_sends: list = []
        self._day_count = 0
        self._day_date: Optional[date] = None

    def _cleanup(self, now: float):
        cutoff_minute = now - 60
        cutoff_hour = now - 3600
        self._minute_sends = [t for t in self._minute_sends if t > cutoff_minute]
        self._hour_sends = [t for t in self._hour_sends if t > cutoff_hour]
        today = date.today()
        if self._day_date != today:
            self._day_date = today
            self._day_count = 0

    def check(self) -> Optional[str]:
        now = time.time()
        with self._lock:
            self._cleanup(now)
            if len(self._minute_sends) >= self.max_per_minute:
                return f"Rate limit: {self.max_per_minute} messages/minute exceeded"
            if len(self._hour_sends) >= self.max_per_hour:
                return f"Rate limit: {self.max_per_hour} messages/hour exceeded"
            if self._day_count >= self.max_per_day:
                return f"Rate limit: {self.max_per_day} messages/day exceeded"
            return None

    def record(self):
        now = time.time()
        with self._lock:
            self._cleanup(now)
            self._minute_sends.append(now)
            self._hour_sends.append(now)
            self._day_count += 1

    @property
    def sends_today(self) -> int:
        with self._lock:
            self._cleanup(time.time())
            return self._day_count


class TelethonUserClient:

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()
        self._rate = RateLimitState()

        self.status = 'disconnected'
        self.last_heartbeat: Optional[float] = None
        self.last_send: Optional[float] = None
        self.last_error: Optional[str] = None

        os.makedirs(SESSION_BASE_DIR, exist_ok=True)

        self._api_id: Optional[int] = None
        self._api_hash: Optional[str] = None
        self._phone: Optional[str] = None
        self._load_credentials()

    def _load_credentials(self):
        try:
            from domains.connections.repo import get_telethon_credentials
            db_creds = get_telethon_credentials(self.tenant_id)
            if db_creds and db_creds.get('api_id') and db_creds.get('api_hash'):
                self._api_id = db_creds['api_id']
                self._api_hash = db_creds['api_hash']
                self._phone = db_creds.get('phone')
                masked = '***' + self._phone[-4:] if self._phone and len(self._phone) >= 4 else '***'
                logger.info(f"Credentials loaded from DB for tenant={self.tenant_id}, phone={masked}")
                return
        except Exception as e:
            logger.warning(f"Could not load telethon credentials from DB for tenant={self.tenant_id}: {e}")

        raw_id = os.environ.get('TELEGRAM_API_ID', '')
        self._api_id = int(raw_id) if raw_id.isdigit() else None
        self._api_hash = os.environ.get('TELEGRAM_API_HASH')
        self._phone = os.environ.get('TELEGRAM_PHONE')
        if self._phone:
            masked = '***' + self._phone[-4:]
            logger.info(f"Credentials loaded from env for tenant={self.tenant_id}, phone={masked}")
        else:
            logger.warning(f"No Telethon credentials found for tenant={self.tenant_id}")

    @property
    def session_path(self) -> str:
        return os.path.join(SESSION_BASE_DIR, self.tenant_id)

    def _build_client(self) -> TelegramClient:
        if not self._api_id or not self._api_hash:
            raise ValueError(f"Missing api_id/api_hash for tenant={self.tenant_id}")
        return TelegramClient(
            self.session_path,
            self._api_id,
            self._api_hash,
        )

    async def connect(self):
        async with self._lock:
            if self._client and self._client.is_connected():
                if await self._client.is_user_authorized():
                    self.status = 'connected'
                    return True
                else:
                    self.status = 'not_authorized'
                    return False
            try:
                from integrations.telegram.user_session import restore_session
                local_path = self.session_path + '.session'
                if not os.path.exists(local_path):
                    restored = restore_session(self.tenant_id)
                    if restored:
                        logger.info(f"Session restored from remote storage for tenant={self.tenant_id}")
                    else:
                        logger.info(f"No remote session available for tenant={self.tenant_id}")
                self._client = self._build_client()
                await self._client.connect()
                if await self._client.is_user_authorized():
                    self.status = 'connected'
                    self.last_heartbeat = time.time()
                    logger.info(f"Telethon connected for tenant={self.tenant_id}")
                    return True
                else:
                    self.status = 'not_authorized'
                    logger.warning(f"Telethon connected but not authorized for tenant={self.tenant_id}")
                    return False
            except Exception as e:
                self.status = 'error'
                self.last_error = str(e)
                logger.exception(f"Telethon connect failed for tenant={self.tenant_id}: {e}")
                return False

    async def get_username(self) -> Optional[str]:
        if not self._client or not self._client.is_connected():
            return None
        try:
            me = await self._client.get_me()
            return me.username if me else None
        except Exception as e:
            logger.warning(f"Failed to get username for tenant={self.tenant_id}: {e}")
            return None

    async def disconnect(self):
        async with self._lock:
            if self._client:
                try:
                    await self._client.disconnect()
                except Exception as e:
                    logger.warning(f"Error during disconnect for tenant={self.tenant_id}: {e}")
                finally:
                    self._client = None
                    self.status = 'disconnected'
                    logger.info(f"Telethon disconnected for tenant={self.tenant_id}")

    async def reconnect(self):
        await self.disconnect()
        return await self.connect()

    async def send_message(self, chat_id, text: str, parse_mode: str = None) -> Dict[str, Any]:
        rate_err = self._rate.check()
        if rate_err:
            logger.warning(f"Rate limited for tenant={self.tenant_id}: {rate_err}")
            return {'success': False, 'error': rate_err}

        async with self._lock:
            if not self._client or not self._client.is_connected():
                ok = await self._reconnect_internal()
                if not ok:
                    return {'success': False, 'error': 'Not connected'}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                msg = await self._client.send_message(chat_id, text, parse_mode=parse_mode)
                self._rate.record()
                self.last_send = time.time()
                self.last_heartbeat = time.time()
                logger.info(f"Message sent via Telethon: tenant={self.tenant_id}, chat={chat_id}, msg_id={msg.id}")
                return {'success': True, 'message_id': msg.id}
            except FloodWaitError as e:
                wait_seconds = e.seconds
                self.last_error = f"FloodWait {wait_seconds}s (attempt {attempt}/{max_retries})"
                logger.warning(f"FloodWaitError for tenant={self.tenant_id}: waiting {wait_seconds}s (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    await asyncio.sleep(wait_seconds + (attempt * 2))
                else:
                    logger.error(f"FloodWait retries exhausted for tenant={self.tenant_id} after {max_retries} attempts")
                    return {'success': False, 'error': f'FloodWait retries exhausted after {max_retries} attempts (last wait: {wait_seconds}s)'}
            except Exception as e:
                self.last_error = str(e)
                logger.exception(f"send_message failed for tenant={self.tenant_id} (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(attempt * 2)
                else:
                    return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Max retries exhausted'}

    async def _reconnect_internal(self) -> bool:
        try:
            if self._client:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            self._client = self._build_client()
            await self._client.connect()
            if await self._client.is_user_authorized():
                self.status = 'connected'
                self.last_heartbeat = time.time()
                logger.info(f"Auto-reconnected for tenant={self.tenant_id}")
                return True
            self.status = 'not_authorized'
            return False
        except Exception as e:
            self.status = 'error'
            self.last_error = str(e)
            logger.error(f"Auto-reconnect failed for tenant={self.tenant_id}: {e}")
            return False

    def send_message_sync(self, chat_id, text: str, parse_mode: str = None) -> Dict[str, Any]:
        return _run_in_bg(self.send_message(chat_id, text, parse_mode=parse_mode))

    def connect_sync(self) -> bool:
        return _run_in_bg(self.connect())

    def disconnect_sync(self):
        return _run_in_bg(self.disconnect())

    def reconnect_sync(self) -> bool:
        return _run_in_bg(self.reconnect())

    def is_connected(self) -> bool:
        return self.status == 'connected' and self._client is not None and self._client.is_connected()

    def get_status(self) -> Dict[str, Any]:
        masked_phone = ('***' + self._phone[-4:]) if self._phone and len(self._phone) >= 4 else None
        return {
            'tenant_id': self.tenant_id,
            'status': self.status,
            'connected': self.is_connected(),
            'last_heartbeat': self.last_heartbeat,
            'last_send': self.last_send,
            'last_error': self.last_error,
            'sends_today': self._rate.sends_today,
            'has_credentials': bool(self._api_id and self._api_hash),
            'has_api_id': bool(self._api_id),
            'masked_phone': masked_phone,
            'has_session_file': os.path.exists(self.session_path + '.session'),
        }

    @property
    def raw_client(self) -> Optional[TelegramClient]:
        return self._client
