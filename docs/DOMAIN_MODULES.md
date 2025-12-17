# PromoStack Domain Modules Reference

## Overview
PromoStack follows a domain-driven structure where each major feature area has its own module under `domains/`. Each domain typically has:
- `handlers.py` - API endpoint handlers
- `repo.py` - Database operations
- `service.py` - Business logic (if complex)

## Domain: Journeys (`domains/journeys/`)

### Purpose
Event-triggered, multi-step conversational flows for Telegram bots via deep links.

### Files
| File | Purpose |
|------|---------|
| `handlers.py` | API endpoints for CRUD operations |
| `repo.py` | Database operations for journeys, steps, sessions |
| `engine.py` | Journey execution engine |
| `scheduler.py` | Background scheduler for delayed messages |

### Key Concepts

#### Step Types
- **message**: Send a message and immediately advance to next step
- **question**: Send a message and wait for user reply
- **delay**: Schedule a message for future delivery
- **wait_for_reply**: Pause until user replies or timeout

#### Session Statuses
- `active`: Currently processing
- `waiting_delay`: Waiting for scheduled message
- `awaiting_reply`: Waiting for user input
- `completed`: Journey finished

#### Deep Link Triggers
Journeys are triggered via Telegram deep links:
```
https://t.me/{bot_username}?start={trigger_code}
```

When a user clicks, the webhook receives `/start {trigger_code}` and matches it to a journey trigger.

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/journeys` | List all journeys |
| POST | `/api/journeys` | Create journey |
| GET | `/api/journeys/{id}` | Get journey details |
| PUT | `/api/journeys/{id}` | Update journey |
| DELETE | `/api/journeys/{id}` | Delete journey |
| GET | `/api/journeys/{id}/steps` | Get journey steps |
| PUT | `/api/journeys/{id}/steps` | Update journey steps |
| GET | `/api/journeys/{id}/triggers` | Get journey triggers |
| POST | `/api/journeys/{id}/triggers` | Create trigger |

### Scheduler Details
The journey scheduler (`scheduler.py`) runs every 30 seconds:
1. Fetches due scheduled messages using `FOR UPDATE SKIP LOCKED`
2. Sends messages via Telegram API
3. Advances sessions to next step
4. Processes wait timeouts for `awaiting_reply` sessions

---

## Domain: Connections (`domains/connections/`)

### Purpose
Manage tenant-specific bot configurations (Signal Bot and Message Bot).

### Files
| File | Purpose |
|------|---------|
| `handlers.py` | API endpoints and bot validation |

### Bot Roles
| Role | Purpose |
|------|---------|
| `signal_bot` | Sends forex trading signals to VIP/FREE channels |
| `message_bot` | Handles user interactions, journeys, support |

### Key Operations

#### Save Bot Connection
1. Validate bot token via Telegram `getMe` API
2. Store token, username, channel ID in `tenant_bot_connections`
3. Set up webhook with unique secret
4. Register webhook URL with Telegram

#### Webhook Setup
Each bot gets a unique webhook secret:
```
https://dash.promostack.io/api/bot-webhook/{webhook_secret}
```

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/connections` | Get all bot connections |
| POST | `/api/connections/{role}` | Save/update bot connection |
| DELETE | `/api/connections/{role}` | Remove bot connection |
| POST | `/api/connections/{role}/test` | Test bot connection |

---

## Domain: Cross Promo (`domains/crosspromo/`)

### Purpose
Automated cross-promotion of VIP signals in FREE channels to drive conversions.

### Files
| File | Purpose |
|------|---------|
| `handlers.py` | API endpoints |
| `service.py` | Business logic and job processing |
| `repo.py` | Database operations |

### Features
1. **Morning News**: Gold market news at 9:00 AM UTC (Mon-Fri)
2. **VIP Teaser**: Teaser message at 10:00 AM UTC (Mon-Fri)
3. **Winning Signal Copy**: Copy successful VIP signals to FREE channel with CTA

### Job Queue
Jobs are stored in `crosspromo_jobs` table:
- Claimed atomically using `FOR UPDATE SKIP LOCKED`
- Processed by background service
- Status tracked: pending → claimed → completed/failed

### Settings
Stored in `tenant_crosspromo_settings`:
- Enable/disable feature
- VIP and FREE channel IDs
- CTA URL for upgrade link
- Morning post time
- Timezone

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/crosspromo/settings` | Get cross promo settings |
| PUT | `/api/crosspromo/settings` | Update settings |
| POST | `/api/crosspromo/test` | Send test message |

---

## Core: Bot Credentials (`core/bot_credentials.py`)

### Purpose
Centralized access to bot tokens and channel IDs. Single source of truth.

### Usage
```python
from core.bot_credentials import BotCredentialResolver

resolver = BotCredentialResolver(tenant_id='entrylab')
creds = resolver.get_bot_credentials('signal_bot')
# Returns: {'token': '...', 'channel_id': '...', 'username': '...'}
```

### Error Handling
Raises `BotNotConfiguredError` with actionable message:
```
BotNotConfiguredError: Signal Bot not configured for tenant 'entrylab'. 
Please configure it in the Connections tab.
```

---

## Core: Tenant Runtime (`core/runtime.py`)

### Purpose
Container for tenant-scoped operations. Ensures all operations are isolated to a single tenant.

### Usage
```python
from core.runtime import TenantRuntime

runtime = TenantRuntime(tenant_id='entrylab')

# Access services
signal_engine = runtime.get_signal_engine()
ai_engine = runtime.get_ai_engine()
telegram_client = runtime.get_telegram_client()
```

### Services Provided
- Signal engine for forex signal generation
- AI engine for message generation
- Telegram client for bot API calls
- Database operations with tenant context

---

## Forex Domain (Not under domains/)

### Files
| File | Purpose |
|------|---------|
| `forex_scheduler.py` | Main scheduler runner |
| `forex_signal_engine.py` | Signal generation logic |
| `forex_config.py` | Configuration management |
| `handlers/forex.py` | API endpoints |

### Strategies (`strategies/`)
| File | Purpose |
|------|---------|
| `base_strategy.py` | Strategy interface |
| `raja_banks.py` | Raja Banks Gold strategy |
| `strategy_loader.py` | Dynamic strategy loading |

### Key Components

#### ForexSchedulerRunner
Runs continuous background tasks:
- Signal checks on 15min and 1h timeframes
- Price monitoring every minute
- Signal guidance updates
- Morning briefings and recaps

#### Signal Engine
Generates trading signals:
1. Fetch price data from Twelve Data
2. Calculate indicators (RSI, ADX, MACD, etc.)
3. Apply strategy rules
4. Generate signal if conditions met
5. Post to Telegram channel

#### Multi-TP System
Signals have multiple take-profit levels:
- TP1: First target (partial close)
- TP2: Second target
- TP3: Final target (full close)

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/forex/signals` | List signals |
| POST | `/api/forex/check` | Trigger manual signal check |
| GET | `/api/forex/config` | Get forex config |
| PUT | `/api/forex/config` | Update forex config |
| GET | `/api/forex/analytics` | Get signal analytics |

---

## Stripe Domain

### Files
| File | Purpose |
|------|---------|
| `handlers/stripe.py` | Webhook handlers |
| `integrations/stripe/` | Stripe API client |

### Webhook Events
| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription |
| `customer.subscription.updated` | Update status |
| `customer.subscription.deleted` | Mark cancelled |
| `invoice.paid` | Log payment |

### Subscription Flow
1. User purchases via Stripe Checkout
2. Webhook receives `checkout.session.completed`
3. Create/update `telegram_subscriptions` record
4. User links Telegram account via `/verify` command
5. Bot grants VIP channel access
