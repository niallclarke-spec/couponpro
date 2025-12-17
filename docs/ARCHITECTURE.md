# PromoStack Architecture Documentation

## Overview
PromoStack is a multi-tenant SaaS platform for marketing automation with two main products:
1. **PromoStack Coupon Bot** - Telegram bot for branded promotional image generation
2. **Forex Signals Bot** - Automated trading signals for XAU/USD with AI-powered messages

## System Architecture

### Dual-Subdomain Architecture
- `admin.promostack.io` - Admin-only access (requires allowlisted email)
- `dash.promostack.io` - Client dashboard for tenants

### Technology Stack
- **Backend**: Python 3.11 with stdlib `http.server`
- **Database**: PostgreSQL (DigitalOcean managed, Neon-backed on Replit)
- **Object Storage**: DigitalOcean Spaces (S3-compatible)
- **External APIs**: Telegram Bot API, Stripe API, Twelve Data (market data), OpenAI
- **Authentication**: Clerk JWT with dynamic issuer-derived JWKS + legacy HMAC cookies
- **Deployment**: DigitalOcean App Platform

### Request Flow
1. Request hits `server.py` (thin HTTP server)
2. Routes to `api/dispatch.py` for API requests or `handlers/pages.py` for pages
3. Middleware in `api/middleware.py` handles auth, logging, CORS
4. Domain handlers process request (e.g., `domains/journeys/handlers.py`)
5. Domain services/repos interact with database
6. Response returned

### Directory Structure
```
/
├── server.py              # Main HTTP server (thin dispatcher)
├── db.py                  # Database pool and schema initialization
├── api/
│   ├── dispatch.py        # Central API router
│   ├── routes.py          # Route definitions
│   └── middleware.py      # Auth, logging, CORS middleware
├── core/
│   ├── bootstrap.py       # Application startup (webhooks, schedulers)
│   ├── runtime.py         # TenantRuntime container (per-tenant context)
│   ├── config.py          # Environment variable access
│   ├── clerk_auth.py      # Clerk JWT verification
│   ├── bot_credentials.py # BotCredentialResolver for centralized bot tokens
│   └── leader.py          # Leader election for single scheduler instance
├── auth/
│   └── clerk_auth.py      # Clerk authentication helpers
├── domains/
│   ├── journeys/          # Telegram conversational flows
│   │   ├── handlers.py    # API handlers
│   │   ├── repo.py        # Database operations
│   │   ├── engine.py      # Journey execution engine
│   │   └── scheduler.py   # Background message scheduler
│   ├── connections/       # Bot token management
│   │   └── handlers.py    # Signal Bot / Message Bot config
│   └── crosspromo/        # Cross-promotion automation
│       ├── handlers.py    # API handlers
│       ├── service.py     # Business logic
│       └── repo.py        # Database operations
├── strategies/            # Forex trading strategies
│   ├── base_strategy.py   # Strategy interface
│   ├── raja_banks.py      # Raja Banks Gold strategy
│   └── strategy_loader.py # Dynamic strategy loading
├── handlers/
│   ├── pages.py           # HTML page handlers
│   ├── forex.py           # Forex API handlers
│   └── stripe.py          # Stripe webhook handlers
├── integrations/
│   ├── telegram/          # Telegram bot integration
│   └── market_data/       # Twelve Data price feeds
├── assets/                # Static files (HTML, CSS, JS)
├── bots/                  # Bot-specific code
│   └── core/
│       └── milestone_tracker.py  # Signal progress notifications
├── forex_scheduler.py     # Main forex scheduler runner
└── .do/app.yaml          # DigitalOcean deployment config
```

### Core Components

#### 1. TenantRuntime (core/runtime.py)
Central container for tenant-scoped operations:
- Manages database connections with tenant context
- Provides access to signal engine, AI engine, Telegram clients
- Ensures tenant isolation across all operations

#### 2. BotCredentialResolver (core/bot_credentials.py)
Centralized bot token management:
- `get_bot_credentials(tenant_id, bot_role)` - Returns bot token and channel ID
- Bot roles: `signal_bot` (forex signals) and `message_bot` (journeys/interactions)
- Raises `BotNotConfiguredError` with actionable message if not configured

#### 3. Leader Election (core/leader.py)
Ensures single scheduler instance across multiple server replicas:
- Uses PostgreSQL advisory locks
- Only leader runs forex scheduler and background tasks
- Other instances retry every 10 seconds

### Background Schedulers

#### Forex Scheduler (forex_scheduler.py)
Runs continuously for a single tenant (configured via `TENANT_ID` env var):
- Signal checks: 15min timeframe every 15 min, 1h timeframe every 30 min
- Price monitoring: Every 1 minute
- Signal guidance: Every 1 minute (10min cooldown)
- Stagnant re-validation: First at 90min, then every 30min
- Hard timeout: 3 hours per signal
- Morning briefing: 6:20 AM UTC
- Daily/weekly recaps: 6:30 AM UTC

**Current Limitation**: Only runs for one tenant. See MULTI_TENANT_FOREX_ROADMAP.md for future plans.

#### Journey Scheduler (domains/journeys/scheduler.py)
Processes delayed messages and wait timeouts:
- Runs every 30 seconds
- Uses `FOR UPDATE SKIP LOCKED` for idempotent processing
- Handles step types: message, question, delay, wait_for_reply

### Authentication Flow

1. **Primary**: Clerk JWT
   - Token in `Authorization: Bearer` header or `__session` cookie
   - JWKS URL derived dynamically from token's `iss` claim
   - Email from `X-Clerk-User-Email` header or `clerk_user_email` cookie
   
2. **Legacy**: HMAC-signed `admin_session` cookie
   - Used for backward compatibility
   - Signed with `ADMIN_PASSWORD` secret

3. **Admin Access Rules**:
   - Requires JWT verification
   - Email must be in admin allowlist
   - Role must be 'admin' in `tenant_users` table

### Multi-Tenancy

All tenant-scoped tables include `tenant_id` column:
- `forex_signals`, `forex_config`, `telegram_subscriptions`
- `bot_users`, `bot_usage`, `broadcast_jobs`
- `journeys`, `journey_steps`, `journey_user_sessions`
- `tenant_crosspromo_settings`, `crosspromo_jobs`

**Tenant Isolation Pattern**:
```python
# All queries filter by tenant_id
cursor.execute("SELECT * FROM forex_signals WHERE tenant_id = %s", (tenant_id,))
```

### External Integrations

#### Telegram
- Coupon Bot: Webhook at `/api/telegram-webhook`
- Forex Bot: Webhook at `/api/forex-telegram-webhook`
- Uses `python-telegram-bot` with AIORateLimiter

#### Stripe
- Webhook at `/api/stripe-webhook`
- Processes subscription events for VIP access
- Source of truth for revenue metrics

#### Twelve Data
- Real-time XAU/USD price data
- Used for signal generation and price monitoring

#### OpenAI
- AI-generated signal messages
- Uses Replit's OpenAI integration
