# Telegram Sender Consolidation - Design Document

## Audit Date: December 2025

## Current State Analysis

### Telegram Send Paths Identified

| Module | Pattern | Status | Issue |
|--------|---------|--------|-------|
| `core/telegram_sender.py` | Async, TTL cache, fresh Bot per send | ✅ CANONICAL | - |
| `forex_bot.py` | Uses `send_to_channel()` from core | ✅ CORRECT | - |
| `bots/core/scheduler.py` | Uses `send_to_channel()` from core | ✅ CORRECT | - |
| `scheduler/messenger.py` | Uses `send_to_channel()` via `_send_channel_message()` | ✅ FIXED | Phase 1 complete |
| `domains/journeys/engine.py` | Direct `requests.post()` | ⚠️ WORKS | Sync context, uses get_bot_credentials() |
| `domains/journeys/scheduler.py` | Direct `requests.post()` | ⚠️ WORKS | Sync thread, uses get_bot_credentials() |
| `integrations/telegram/client.py` | Sync `requests.post()` | ⚠️ WORKS | Separate sync client |
| `domains/crosspromo/service.py` | Uses `integrations/telegram/client` | ✅ CORRECT | Correct for sync |
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

## Phase 1 Completion Status

**Completed: December 18, 2025**

### Changes Made

1. **`scheduler/messenger.py` refactored**:
   - Created `_send_channel_message()` helper method that routes all sends through `core.telegram_sender.send_to_channel()`
   - Added proper imports: `send_to_channel`, `SendResult` from `core/telegram_sender`, `SIGNAL_BOT` from `core/bot_credentials`
   - Refactored 7 send methods to use the new helper
   - Added proper `SendResult`-based error handling with consistent logging
   - Eliminated all broken `self.bot.bot.*` patterns

2. **Methods updated**:
   - `send_tp1_celebration()` - Now uses `_send_channel_message()`
   - `send_tp2_celebration()` - Now uses `_send_channel_message()`
   - `send_tp3_celebration()` - Now uses `_send_channel_message()`
   - `send_sl_hit_message()` - Now uses `_send_channel_message()`
   - `send_profit_locked_message()` - Now uses `_send_channel_message()`
   - `send_breakeven_exit_message()` - Now uses `_send_channel_message()`
   - `send_milestone_message()` - Now uses `_send_channel_message()`

3. **Verification completed**:
   - All imports test passed
   - Pattern verification confirmed no broken `self.bot.bot.*` or `telegram.Bot()` usage outside canonical sender
   - Server starts and runs without errors
   - Architect review approved

### Sync vs Async Pattern Decision

Two patterns are now established and working:

| Context | Pattern | Usage |
|---------|---------|-------|
| Async scheduler/signals | `core/telegram_sender.send_to_channel()` | Forex signals, milestones, TP/SL |
| Sync HTTP handlers | `requests.post()` with `get_bot_credentials()` | Journeys, broadcasts |

Both patterns are valid and correct for their contexts. The key rule is: **No direct `telegram.Bot()` instantiation** outside of `core/telegram_sender.py`.

## Future Considerations

1. **Journeys Code Duplication**: `domains/journeys/engine.py` and `domains/journeys/scheduler.py` both have inline `requests.post()` implementations. Future consolidation could move these to use `integrations/telegram/client.py` for consistency.

2. **Legacy Coupon Bot** (`telegram_bot.py`): Uses different architecture (webhook handler) - leave as-is, different use case.

3. **Cross-Promo Service**: Already uses `integrations/telegram/client.py` correctly for sync operations.

4. **Pre-existing LSP issue**: `domains/journeys/scheduler.py` line 211 has a type annotation issue (`None` passed where `int` expected). Minor, not blocking.
