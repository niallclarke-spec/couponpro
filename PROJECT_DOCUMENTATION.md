# PromoStack/EntryLab - Project Documentation

> **Purpose**: Technical documentation for developers and AI assistants working with this codebase.

---

## Table of Contents
1. [Architecture Overview (Current)](#1-architecture-overview-current)
2. [Startup & Side Effects](#2-startup--side-effects)
3. [Current Directory Layout](#3-current-directory-layout)
4. [API Surface](#4-api-surface)
5. [Data Model](#5-data-model)
6. [Domain Modules](#6-domain-modules)
7. [Integrations](#7-integrations)
8. [Workers & Background Jobs](#8-workers--background-jobs)
9. [Configuration & Secrets](#9-configuration--secrets)
10. [Known Limitations / Single-Tenant Reality](#10-known-limitations--single-tenant-reality)
11. [Frontend](#11-frontend)
12. [What Changed Since Last Version](#12-what-changed-since-last-version)
13. [Smoke Tests & Invariants Checklist](#13-smoke-tests--invariants-checklist)

---

## 1. Architecture Overview (Current)

PromoStack is a **single-process Python 3.11 application** combining:
- **Coupon Bot**: Telegram bot for promotional image generation
- **Forex Signals Bot**: Automated XAU/USD trading signals
- **Subscription Billing**: Stripe-powered VIP access management
- **Admin Dashboard**: Unified management interface

### Architecture Characteristics (Post-Refactor)

| Component | Lines | Purpose |
|-----------|-------|---------|
| `server.py` | **766** | Thin HTTP entrypoint: domain routing + static serving + startup |
| `api/routes.py` | ~100 | Route definitions with metadata (auth, db requirements) |
| `api/middleware.py` | ~50 | Request gating (auth checks, db availability) |
| `domains/*` | ~1,200 | Extracted handler functions by business domain |
| `integrations/*` | ~300 | External service handlers (Stripe, Telegram) |
| `workers/*` | ~30 | Wrapper namespace for background jobs |
| `core/*` | ~200 | App context and bootstrap (side-effect control) |

### Key Design Decisions

1. **server.py is thin**: No longer a monolith. Contains only:
   - HTTP server class with request routing
   - Static file serving
   - Domain dispatch logic
   - Startup orchestration

2. **api/routes.py + api/middleware.py**: Declarative routing model
   - Routes defined as dataclasses with `path`, `method`, `auth_required`, `db_required`
   - Middleware applies checks before dispatch

3. **domains/* contains extracted handlers**: Business logic separated by domain
   - `domains/subscriptions/handlers.py` - Telegram subscription management
   - `domains/coupons/handlers.py` - Campaign/coupon logic
   - `domains/forex/handlers.py` - Trading signal management

4. **integrations/* contains external service handlers**:
   - `integrations/telegram/webhooks.py` - Both bot webhooks
   - `integrations/stripe/webhooks.py` - Payment webhooks

5. **workers/* is wrapper namespace**: Thin re-exports around background jobs
   - Does not contain implementation logic
   - Provides clean import paths for bootstrap

6. **core/app_context.py + core/bootstrap.py controls side effects**:
   - `create_app_context()` - Pure function, no side effects
   - `start_app(ctx)` - All side effects happen here

---

## 2. Startup & Side Effects

### Critical Invariant

**Importing `server.py` must NOT start any side effects.**

This is enforced by the two-phase startup:

### Phase 1: Context Creation (Pure)

```python
# In server.py at startup:
from core.app_context import create_app_context

ctx = create_app_context()  # No side effects - just reads env vars
```

`create_app_context()` returns an `AppContext` object with:
- Feature flags (database_available, telegram_bot_available, etc.)
- Bot tokens (read from environment)
- No imports of side-effect modules

### Phase 2: Bootstrap (Side Effects)

```python
from core.bootstrap import start_app

start_app(ctx)  # ALL side effects happen here
```

`start_app(ctx)` performs:
1. Database module import and schema initialization
2. Telegram webhook registration (both bots)
3. Forex scheduler startup in background thread
4. Stripe client initialization

### Scheduler Startup Guarantee

**The scheduler starts exactly once.** Enforced by:
- `_started` flag in `core/bootstrap.py`
- Idempotent `start_app()` - calling twice has no effect
- Single background thread with daemon=True

### Webhooks Register Only in `start_app(ctx)`

No webhook registration happens at import time. Both Telegram bots and Stripe webhooks are configured only when `start_app(ctx)` is called.

---

## 3. Current Directory Layout

```
promostack/
├── server.py                    # HTTP server entrypoint (766 lines)
├── db.py                        # Database operations + migrations
├── stripe_client.py             # Stripe API wrapper
│
├── core/                        # Application lifecycle
│   ├── __init__.py
│   ├── app_context.py           # Pure context creation
│   ├── bootstrap.py             # Side-effect startup
│   └── config.py                # Environment configuration
│
├── api/                         # Routing layer
│   ├── __init__.py
│   ├── routes.py                # Route definitions
│   └── middleware.py            # Auth/DB checks
│
├── domains/                     # Business logic by domain
│   ├── subscriptions/
│   │   ├── __init__.py
│   │   └── handlers.py          # Telegram subscription handlers
│   ├── coupons/
│   │   ├── __init__.py
│   │   └── handlers.py          # Campaign/coupon handlers
│   └── forex/
│       ├── __init__.py
│       └── handlers.py          # Forex signal handlers
│
├── integrations/                # External service handlers
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── webhooks.py          # Both bot webhooks
│   └── stripe/
│       ├── __init__.py
│       └── webhooks.py          # Payment webhooks
│
├── workers/                     # Background job wrappers
│   ├── __init__.py              # Exports all workers
│   ├── scheduler.py             # Re-exports start_forex_scheduler
│   ├── price_monitor.py         # Re-exports price_monitor singleton
│   └── milestone_tracker.py     # Re-exports milestone_tracker singleton
│
├── bots/                        # Bot implementation
│   ├── __init__.py
│   ├── core/
│   │   ├── scheduler.py         # SignalBotScheduler class
│   │   ├── price_monitor.py     # PriceMonitor class
│   │   ├── milestone_tracker.py # MilestoneTracker class
│   │   ├── ai_guidance.py       # AI message generation
│   │   ├── signal_generator.py  # Signal generation logic
│   │   └── bot_manager.py       # Bot/strategy management
│   └── strategies/
│       ├── base.py              # Abstract base strategy
│       ├── raja_banks.py        # Primary strategy
│       ├── aggressive.py        # High risk variant
│       └── conservative.py      # Low risk variant
│
├── forex_scheduler.py           # Async scheduler loop
├── forex_bot.py                 # Forex bot initialization
├── forex_signals.py             # Signal generation
├── forex_api.py                 # Twelve Data client
├── forex_ai.py                  # AI message generation
├── indicator_config.py          # Technical indicator settings
│
├── telegram_bot.py              # Coupon bot logic
├── telegram_image_gen.py        # Pillow image generation
├── coupon_validator.py          # FunderPro API
├── object_storage.py            # DO Spaces wrapper
│
├── admin.html                   # Admin dashboard SPA (9,290 lines)
├── index.html                   # Public coupon generator
├── campaign.html                # Campaign submission page
│
├── ARCHITECTURE.md              # Detailed technical architecture
├── PROJECT_DOCUMENTATION.md     # This file
├── replit.md                    # User preferences + decisions
└── requirements.txt             # Python dependencies
```

---

## 4. API Surface

### Route Matching Order

1. Domain-based routing (admin.promostack.io, dash.promostack.io)
2. Middleware checks (auth_required, db_required)
3. Domain handler dispatch
4. Static page serving (/admin, /campaign/)
5. Inline handlers (check-auth, day-of-week-stats, retention-rates)
6. Static file serving (default)

### Endpoints by Domain

#### Authentication (Inline in server.py)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/check-auth` | No | Verify session |
| POST | `/api/login` | No | Admin login |
| POST | `/api/logout` | No | Clear session |

#### Subscriptions Domain (`domains/subscriptions/handlers.py`)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/telegram-subscriptions` | Yes | List VIP subscribers |
| GET | `/api/telegram/revenue-metrics` | Yes | Stripe revenue data |
| GET | `/api/telegram/conversion-analytics` | Yes | Conversion funnel |
| GET | `/api/telegram/billing/{id}` | Yes | Subscriber billing history |
| GET | `/api/telegram/check-access/{username}` | No | Check VIP access |
| POST | `/api/telegram/grant-access` | Yes | Grant VIP access |
| POST | `/api/telegram/revoke-access` | Yes | Revoke VIP access |
| POST | `/api/telegram/cancel-subscription` | Yes | Cancel subscription |
| POST | `/api/telegram/delete-subscription` | Yes | Delete subscription |
| POST | `/api/telegram/clear-all` | Yes | Clear all subscriptions |
| POST | `/api/telegram/cleanup-test-data` | Yes | Remove test data |

#### Coupons Domain (`domains/coupons/handlers.py`)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/campaigns` | No | List campaigns |
| GET | `/api/campaigns/{id}` | No | Get campaign |
| GET | `/api/campaigns/{id}/submissions` | Yes | Campaign submissions |
| GET | `/api/bot-stats` | Yes | Bot usage analytics |
| GET | `/api/bot-users` | Yes | Bot user list |
| GET | `/api/broadcast-status/{id}` | Yes | Broadcast job status |
| GET | `/api/broadcast-jobs` | Yes | List broadcast jobs |
| GET | `/api/user-activity/{id}` | Yes | User activity history |
| GET | `/api/invalid-coupons` | Yes | Invalid coupon log |
| POST | `/api/validate-coupon` | No | FunderPro validation |
| POST | `/api/broadcast` | Yes | Send broadcast message |
| POST | `/api/upload-template` | Yes | Upload template |
| POST | `/api/upload-overlay` | Yes | Upload overlay |
| POST | `/api/delete-template` | Yes | Delete template |
| POST | `/api/toggle-telegram-template` | Yes | Toggle template visibility |
| POST | `/api/clear-telegram-cache` | Yes | Clear template cache |
| POST | `/api/regenerate-index` | Yes | Regenerate template index |

#### Forex Domain (`domains/forex/handlers.py`)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/forex-signals` | Yes | List signals |
| GET | `/api/forex-stats` | Yes | Performance stats |
| GET | `/api/forex-config` | Yes | Strategy config |
| GET | `/api/signal-bot/status` | Yes | Bot status |
| GET | `/api/signal-bot/signals` | Yes | Active signals |
| GET | `/api/forex-tp-config` | Yes | TP configuration |
| GET | `/api/forex/xauusd-sparkline` | Yes | Price sparkline |
| POST | `/api/forex-config` | Yes | Update config |
| POST | `/api/forex-tp-config` | Yes | Update TP config |
| POST | `/api/signal-bot/set-active` | Yes | Set active strategy |
| POST | `/api/signal-bot/cancel-queue` | Yes | Cancel queued signals |

#### Webhooks (`integrations/*/webhooks.py`)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/telegram-webhook` | No | Coupon bot webhook |
| POST | `/api/forex-telegram-webhook` | No | Forex bot webhook |
| POST | `/api/stripe/webhook` | No | Stripe payment webhook |

#### Analytics (Inline in server.py)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/day-of-week-stats` | Yes | Day-of-week analytics |
| GET | `/api/retention-rates` | Yes | User retention data |
| GET | `/api/telegram-channel-stats` | Yes | Channel statistics |

---

## 5. Data Model

### Table Ownership by Domain

| Table | Owner Domain | Purpose |
|-------|--------------|---------|
| `campaigns` | Coupons | Marketing campaigns |
| `submissions` | Coupons | Campaign submissions |
| `bot_usage` | Coupons | Coupon bot analytics |
| `bot_users` | Coupons | Telegram user profiles |
| `broadcast_jobs` | Coupons | Admin message queue |
| `forex_signals` | Forex | Trading signals |
| `forex_config` | Forex | Strategy parameters |
| `bot_config` | Shared | General bot settings |
| `signal_narrative` | Forex | AI narratives |
| `recent_phrases` | Forex | AI deduplication |
| `telegram_subscriptions` | Subscriptions | VIP subscribers |
| `processed_webhook_events` | Integrations | Webhook idempotency |

### Key Schema: forex_signals
```sql
CREATE TABLE forex_signals (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(4),           -- 'BUY' or 'SELL'
    entry_price DECIMAL(10,5),
    stop_loss DECIMAL(10,5),
    take_profit DECIMAL(10,5),      -- TP1
    take_profit_2 DECIMAL(10,5),    -- TP2
    take_profit_3 DECIMAL(10,5),    -- TP3
    status VARCHAR(20),             -- active, tp1_hit, tp2_hit, closed_tp, closed_sl, expired
    effective_sl DECIMAL(10,5),     -- Actual SL for P&L (moves with breakeven)
    breakeven_set BOOLEAN,
    tp1_hit BOOLEAN,
    tp2_hit BOOLEAN,
    tp3_hit BOOLEAN,
    milestones_sent TEXT,           -- Comma-separated milestone IDs
    last_milestone_at TIMESTAMP,
    indicators_used TEXT,           -- JSON of triggering indicators
    created_at TIMESTAMP,
    closed_at TIMESTAMP,
    close_price DECIMAL(10,5)
);
```

### Key Schema: telegram_subscriptions
```sql
CREATE TABLE telegram_subscriptions (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    plan_type VARCHAR(50),
    amount_paid DECIMAL(10,2),
    telegram_username VARCHAR(255),
    telegram_user_id BIGINT,
    channel_joined BOOLEAN,
    access_revoked BOOLEAN,
    free_signup_at TIMESTAMP,       -- For conversion tracking
    is_converted BOOLEAN,
    converted_at TIMESTAMP,
    conversion_days INTEGER,
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    created_at TIMESTAMP
);
```

---

## 6. Domain Modules

### domains/subscriptions/handlers.py

Handles Telegram VIP subscription management:
- Subscriber CRUD operations
- Revenue metrics (delegates to Stripe client)
- Conversion analytics
- Access grant/revoke
- Billing history

**Dependencies**: `db.py`, `stripe_client.py`

### domains/coupons/handlers.py

Handles coupon bot and campaign operations:
- Campaign management
- Template upload/delete
- Bot analytics
- Broadcast messaging
- Coupon validation (FunderPro)

**Dependencies**: `db.py`, `object_storage.py`, `coupon_validator.py`

### domains/forex/handlers.py

Handles forex signal management:
- Signal listing and stats
- Strategy configuration
- Bot status monitoring
- TP configuration

**Dependencies**: `db.py`, `forex_scheduler.py`, `bots/core/*`

---

## 7. Integrations

### Stripe (`integrations/stripe/webhooks.py`)

Handles Stripe webhook events:
- `checkout.session.completed` - New subscription
- `customer.subscription.updated` - Plan changes
- `customer.subscription.deleted` - Cancellation
- `invoice.payment_failed` - Failed payment

**Idempotency**: Uses `processed_webhook_events` table to prevent duplicate processing.

### Telegram (`integrations/telegram/webhooks.py`)

Two separate webhook handlers:
- `handle_coupon_telegram_webhook()` - Coupon bot interactions
- `handle_forex_telegram_webhook()` - Forex bot join tracking

**Both return 200 immediately** to prevent Telegram retry storms.

### OpenAI

Used via Replit AI integration for:
- Signal announcement messages
- Milestone celebration messages
- Morning briefings and recaps

**Client**: `OpenAI` from `openai` package with Replit base URL.

### Twelve Data (forex_api.py)

Market data provider for XAU/USD prices:
- Real-time price quotes
- OHLC candle data
- Technical indicator calculations

---

## 8. Workers & Background Jobs

### Worker Package Structure

```
workers/
├── __init__.py              # Exports: start_forex_scheduler, price_monitor, milestone_tracker
├── scheduler.py             # Re-exports from forex_scheduler
├── price_monitor.py         # Re-exports from bots/core/price_monitor
└── milestone_tracker.py     # Re-exports from bots/core/milestone_tracker
```

### Why Wrappers?

The `workers/` package provides:
1. **Clean import paths** for bootstrap
2. **Single namespace** for all background workers
3. **No internal logic modification** - just re-exports
4. **Future extensibility** for new workers

### How Workers Start

1. `start_app(ctx)` is called in `server.py`
2. Bootstrap imports `from workers.scheduler import start_forex_scheduler`
3. Scheduler runs in background thread with `daemon=True`
4. Price monitor and milestone tracker are singletons used by scheduler

### Scheduler Intervals

| Task | Interval | Purpose |
|------|----------|---------|
| Signal check (15m) | 15 min | Generate new signals |
| Signal check (1h) | 30 min | Higher timeframe check |
| Price monitoring | 1 min | TP/SL detection |
| Signal guidance | 1 min | Milestone notifications |
| Stagnant re-validation | 90 min initial, 30 min after | Check indicator validity |

---

## 9. Configuration & Secrets

### core/config.py

Centralized configuration class:

```python
class Config:
    @staticmethod
    def get_port() -> int
    
    @staticmethod
    def get_admin_password() -> str
    
    @staticmethod
    def get_database_url() -> str
    
    @staticmethod
    def is_development() -> bool
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Yes | PostgreSQL connection |
| `ADMIN_PASSWORD` | Yes | Admin authentication |
| `TELEGRAM_BOT_TOKEN` | Yes | Coupon bot |
| `FOREX_BOT_TOKEN` | Prod | Forex bot (production) |
| `ENTRYLAB_TEST_BOT` | Dev | Forex bot (development) |
| `STRIPE_SECRET_KEY` | Yes | Stripe API |
| `STRIPE_WEBHOOK_SECRET` | Prod | Webhook signature verification |
| `TWELVE_DATA_API_KEY` | Yes | Market data |
| `SPACES_ACCESS_KEY` | Yes | DO Spaces |
| `SPACES_SECRET_KEY` | Yes | DO Spaces |
| `SPACES_BUCKET` | Yes | Template storage bucket |
| `SPACES_REGION` | Yes | DO region |
| `FUNDERPRO_PRODUCT_ID` | Yes | Coupon validation |
| `AI_INTEGRATIONS_OPENAI_API_KEY` | Auto | Replit AI integration |
| `AI_INTEGRATIONS_OPENAI_BASE_URL` | Auto | Replit AI integration |

### Platform Config vs Runtime State

| Type | Location | Example |
|------|----------|---------|
| Platform config | Environment variables | `DATABASE_URL`, `ADMIN_PASSWORD` |
| Runtime state | `AppContext` | `database_available`, `forex_scheduler_available` |
| Feature config | Database tables | `forex_config`, `bot_config` |

---

## 10. Known Limitations / Single-Tenant Reality

### Single-Tenant Design

**Tenant isolation is NOT implemented.** Current assumptions:

1. **Global bots**: One coupon bot, one forex bot for entire platform
2. **Global scheduler**: Single scheduler instance for all signals
3. **Shared database**: All data in one PostgreSQL database
4. **Shared object storage**: One Spaces bucket for all templates
5. **Single admin**: One admin password for entire system

### No Per-Tenant Isolation

- No tenant_id columns in database
- No request-scoped tenant context
- No multi-bot support per tenant
- No per-tenant configuration

### Process Restart Behavior

- Server restart = scheduler restart
- No scheduler persistence across restarts
- Active signals continue from database state
- No distributed locking

### Horizontal Scaling

**Not supported.** Running multiple instances would cause:
- Multiple scheduler threads
- Duplicate signal generation
- Webhook race conditions

---

## 11. Frontend

### admin.html (9,290 lines)

Single-file SPA containing:
- HTML structure
- CSS styles (dark navy theme)
- JavaScript application logic
- Hash-based routing (#product/view)
- All admin UI components

### Structure (Current, Not Proposed Rewrite)

```html
<!-- HTML: ~500 lines -->
<div id="app">
  <nav id="product-switcher">...</nav>
  <nav id="main-nav">...</nav>
  <main id="content">...</main>
</div>

<!-- CSS: ~2,000 lines -->
<style>
  :root { --bg-primary: #081028; ... }
  /* Component styles */
</style>

<!-- JavaScript: ~6,500 lines -->
<script>
  // Router, API client, view controllers
  // All product views (templates, analytics, signals, subscriptions)
</script>
```

### Design System

- **Background**: #081028 (dark navy)
- **Accent**: #CB3CFF (purple)
- **Sidebar**: 60px product switcher + 240px feature nav
- **Responsive**: Collapsible sidebars on mobile

### index.html / campaign.html

Smaller public-facing pages:
- `index.html`: Public coupon generator
- `campaign.html`: Campaign submission form

---

## 12. What Changed Since Last Version

### Major Refactoring (December 2025)

| Before | After |
|--------|-------|
| server.py: 3,686 lines | server.py: 766 lines (79% reduction) |
| All handlers inline | Handlers extracted to domains/* |
| Direct module imports | workers/* wrapper namespace |
| Side effects at import | Two-phase startup (context + bootstrap) |
| No routing metadata | api/routes.py with auth/db flags |
| Ad-hoc auth checks | api/middleware.py centralized |

### New Packages Added

- `core/` - App context and bootstrap
- `api/` - Routes and middleware
- `domains/` - Business logic handlers
- `integrations/` - External service handlers
- `workers/` - Background job wrappers

### Files Deleted

- ~2,920 lines of duplicate inline handlers removed from server.py

### Invariants Introduced

1. Import-time purity: importing server.py starts nothing
2. Single scheduler: exactly one scheduler thread
3. Bootstrap-only webhooks: no webhook registration at import
4. Middleware gate: all auth/db checks in one place

---

## 13. Smoke Tests & Invariants Checklist

Run after any refactoring to verify system integrity:

### A) Import Invariant

```bash
python3 -c "import server; print('server import ok')"
```
**Expected**: Prints "server import ok" with no scheduler/webhook logs.

### B) Scheduler Count

```bash
python3 server.py &
sleep 3
grep -c "FOREX SIGNALS SCHEDULER STARTED" /tmp/logs/Server_*.log | tail -1
```
**Expected**: Exactly `1`.

### C) Core Pages

```bash
curl -s http://localhost:5000/admin | head -2
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://localhost:5000/assets/promostack-logo.png
```
**Expected**: HTML for admin, `200 image/png` for asset.

### D) Auth Endpoint

```bash
curl -s http://localhost:5000/api/check-auth
```
**Expected**: `{"authenticated": false}` (when not logged in).

### E) Webhooks Return 200

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/api/telegram-webhook
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/api/forex-telegram-webhook
curl -s -o /dev/null -w "%{http_code}\n" -X POST -d '{}' http://localhost:5000/api/stripe/webhook
```
**Expected**: All return `200`.

### F) Domain Endpoints (Unauthorized)

```bash
curl -s http://localhost:5000/api/telegram-subscriptions
curl -s http://localhost:5000/api/forex-config
curl -s http://localhost:5000/api/bot-stats
```
**Expected**: All return `{"error": "Unauthorized"}`.

### G) Line Count Check

```bash
wc -l server.py
```
**Expected**: ~766 lines (not thousands).

---

## Document Version
- **Created**: December 12, 2025
- **Last Updated**: December 13, 2025
- **Architecture Version**: Post-refactor (Step 10 complete)
