# Telegram Sender Consolidation - Design Document

## Audit Date: December 2025

## Current State Analysis

### Telegram Send Paths Identified

| Module | Pattern | Status | Issue |
|--------|---------|--------|-------|
| `core/telegram_sender.py` | Async, TTL cache, fresh Bot per send | ✅ CANONICAL | - |
| `forex_bot.py` | Uses `send_to_channel()` from core | ✅ CORRECT | - |
| `bots/core/scheduler.py` | Uses `send_to_channel()` from core | ✅ CORRECT | - |
| `scheduler/messenger.py` | Uses `self.bot.bot.send_message()` | ❌ BROKEN | AttributeError |
| `domains/journeys/engine.py` | Direct `requests.post()` | ⚠️ WORKS | Inconsistent |
| `integrations/telegram/client.py` | Sync `requests.post()` | ⚠️ WORKS | Separate sync client |
| `domains/crosspromo/service.py` | Uses `integrations/telegram/client` | ⚠️ WORKS | Correct for sync |
| `telegram_bot.py` | Legacy coupon bot with `Application.builder()` | ⚠️ LEGACY | Different use case |

### Root Cause of Bug

`scheduler/messenger.py` tries to access `self.bot.bot.send_message()` where:
- `self.bot` = `ForexTelegramBot` instance (from `runtime.get_telegram_bot()`)
- `ForexTelegramBot` has NO `.bot` attribute
- It was refactored to use `send_to_channel()` internally, removing the cached Bot

The code also accesses `self.bot.channel_id` which doesn't exist.

## Target Architecture

### Canonical Send Path (Async)
```
core/telegram_sender.py
├── send_message(tenant_id, bot_role, chat_id, text, ...)
├── send_to_channel(tenant_id, bot_role, text, channel_type='vip'|'free'|'default')
├── copy_message(tenant_id, bot_role, from_chat_id, to_chat_id, message_id)
└── validate_bot_credentials(tenant_id, bot_role)
```

### Sync Client (For HTTP Handlers)
```
integrations/telegram/client.py
├── send_message(bot_token, chat_id, text, ...)
├── copy_message(bot_token, from_chat_id, to_chat_id, message_id)
└── forward_message(bot_token, from_chat_id, to_chat_id, message_id)
```

### Rules

1. **Scheduler/async code** → Use `core/telegram_sender`
2. **HTTP handlers (sync)** → Use `integrations/telegram/client` with tokens from `get_bot_credentials()`
3. **No direct `telegram.Bot()` instantiation** outside of `core/telegram_sender`
4. **No `self.bot.bot.*` patterns** anywhere

## Phase 1 Changes

### 1. Refactor `scheduler/messenger.py`

**Before (BROKEN):**
```python
await self.bot.bot.send_message(
    chat_id=self.bot.channel_id,
    text=message,
    parse_mode='HTML'
)
```

**After (FIXED):**
```python
from core.telegram_sender import send_to_channel
from core.bot_credentials import SIGNAL_BOT

result = await send_to_channel(
    tenant_id=self.tenant_id,
    bot_role=SIGNAL_BOT,
    text=message,
    parse_mode='HTML',
    channel_type='vip'
)
if not result.success:
    logger.error(f"Send failed: {result.error}")
```

### 2. Methods to Fix in `scheduler/messenger.py`

| Method | Line | Fix |
|--------|------|-----|
| `send_tp1_celebration` | 55 | Replace with `send_to_channel()` |
| `send_tp2_celebration` | 70 | Replace with `send_to_channel()` |
| `send_tp3_celebration` | 85 | Replace with `send_to_channel()` |
| `send_sl_hit_message` | 100 | Replace with `send_to_channel()` |
| `send_profit_locked_message` | 115 | Replace with `send_to_channel()` |
| `send_breakeven_exit_message` | 130 | Replace with `send_to_channel()` |
| `send_milestone_message` | 146 | Replace with `send_to_channel()` |

### 3. Keep Working Methods Unchanged

These methods delegate to `ForexTelegramBot` which already uses correct pattern:
- `post_signal()` → calls `self.bot.post_signal()` ✅
- `post_signal_expired()` → calls `self.bot.post_signal_expired()` ✅
- `post_revalidation_update()` → calls `self.bot.post_revalidation_update()` ✅
- `post_signal_timeout()` → calls `self.bot.post_signal_timeout()` ✅

## Future Considerations

1. **Journeys Engine**: Currently uses `requests.post()` directly - could be migrated to sync client for consistency but works correctly now.

2. **Legacy Coupon Bot** (`telegram_bot.py`): Uses different architecture (webhook handler) - leave as-is, different use case.

3. **Cross-Promo Service**: Uses `integrations/telegram/client.py` correctly for sync operations.
