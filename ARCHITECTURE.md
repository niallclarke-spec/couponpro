# Architecture Documentation

Internal technical documentation for PromoStack. Audience: Senior developers joining the project.

---

## 1. High-Level Overview

PromoStack is a Python 3.11 single-process application that combines:

- **Coupon/Campaign System**: Telegram bot for coupon validation, campaign management, broadcast messaging
- **Forex Signals**: Automated XAU/USD trading signals via technical analysis, delivered to Telegram channels
- **Subscription Billing**: Stripe integration for recurring payments, automatic Telegram channel access management
- **Telegram Bots**: Two separate bots - coupon bot (user interactions) and forex bot (signal delivery)

### Architecture Characteristics

- **Single-process**: Everything runs in one Python process - HTTP server, scheduler, signal monitors
- **Custom HTTP server**: Built on `http.server.SimpleHTTPRequestHandler`, not Flask/FastAPI
- **No framework**: Raw HTTP handling with manual routing, middleware, and response serialization
- **PostgreSQL database**: Shared database for all domains (campaigns, signals, subscriptions)
- **Background threads**: Forex scheduler runs in a daemon thread within the main process

### Technology Stack

| Layer | Technology |
|-------|------------|
| HTTP Server | Python `http.server` (stdlib) |
| Database | PostgreSQL via `psycopg2` connection pool |
| External APIs | Telegram Bot API, Stripe API, Twelve Data (market data), OpenAI |
| Object Storage | DigitalOcean Spaces (S3-compatible) |

---

## 2. Startup & Lifecycle

### Entrypoint: `server.py`

```
python3 server.py
```

The startup sequence has two distinct phases to ensure no side effects at import time:

### Phase 1: Context Creation (Pure)

```python
# In server.py at module level (lines ~650-680):
from core.app_context import create_app_context
from core.bootstrap import start_app

ctx = create_app_context()  # PURE: No side effects
```

`create_app_context()` in `core/app_context.py`:
- Reads environment variables
- Sets availability flags (`database_available`, `telegram_bot_available`, etc.)
- Returns `AppContext` dataclass
- **Does NOT**: Import db module, make network calls, start threads, register webhooks

### Phase 2: Bootstrap (Side Effects)

```python
start_app(ctx)  # ALL side effects happen here
```

`start_app()` in `core/bootstrap.py`:
1. Imports and initializes database (`db.db_pool.initialize_schema()`)
2. Registers Telegram coupon bot webhook
3. Sets up Forex bot webhook URL
4. Starts Forex scheduler in daemon thread
5. Initializes Stripe client

**Critical invariant**: `start_app()` is **idempotent** - protected by `_started` flag.

### Scheduler Startup

The forex scheduler runs in a dedicated daemon thread:

```python
# In bootstrap.py:
scheduler_thread = threading.Thread(target=run_forex_scheduler, daemon=True)
scheduler_thread.start()
```

The scheduler (`forex_scheduler.py`) runs an async event loop:
- Signal checks every 15 minutes
- Active signal monitoring every 1 minute
- Milestone/guidance checks every 1 minute
- Daily/weekly recaps at scheduled times

### HTTP Server Start

After bootstrap, the HTTP server starts:

```python
with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    httpd.serve_forever()
```

---

## 3. Routing & Request Flow

### Route Definitions: `api/routes.py`

Routes are defined as `Route` dataclasses:

```python
@dataclass
class Route:
    method: str           # 'GET' or 'POST'
    path: str             # URL path
    handler: str          # Method name on handler class
    auth_required: bool   # Require session auth
    db_required: bool     # Require database availability
    is_prefix: bool       # Match prefix instead of exact
    contains: Optional[str]  # Additional substring match
```

Three route lists:
- `GET_ROUTES`: API GET endpoints
- `POST_ROUTES`: API POST endpoints  
- `PAGE_ROUTES`: HTML page serving

### Route Matching: `match_route()`

```python
route = match_route('GET', parsed_path.path, GET_ROUTES + PAGE_ROUTES)
```

Matching logic:
1. Check method matches
2. If `is_prefix=True`: `path.startswith(route.path)`
3. If `contains` set: require substring present
4. Otherwise: exact match

**Order matters**: More specific patterns must come before general ones.

### Middleware: `api/middleware.py`

Before handlers execute, middleware checks run:

```python
if not apply_route_checks(route, self, DATABASE_AVAILABLE):
    return  # 401 or 503 already sent
```

`apply_route_checks()`:
1. If `db_required` and database unavailable → 503
2. If `auth_required` and `check_auth()` fails → 401

### Request Dispatch

After middleware passes, `server.py` dispatches to domain handlers:

```python
# In do_GET():
if parsed_path.path.startswith('/api/telegram/check-access/'):
    subscription_handlers.handle_telegram_check_access(self)
    return
elif parsed_path.path == '/api/campaigns':
    coupon_handlers.handle_campaigns_list(self)
    return
# ... etc
```

Each handler receives the `MyHTTPRequestHandler` instance and is responsible for:
- Parsing request body/query params
- Business logic
- Sending response (`send_response()`, `send_header()`, `wfile.write()`)

### Static File Serving

Unmatched GET requests fall through to `super().do_GET()` which serves static files from the current directory via `SimpleHTTPRequestHandler`.

### Authentication

Session-based auth using HMAC-signed cookies:

```python
def create_signed_session():
    expiry = int(time.time()) + SESSION_TTL  # 24h
    payload = str(expiry)
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"

def verify_signed_session(token):
    payload, signature = token.rsplit('.', 1)
    # Verify expiry and HMAC signature
```

No server-side session storage - the cookie is self-validating.

---

## 4. Domain Modules

### Structure

```
domains/
├── subscriptions/
│   ├── __init__.py
│   └── handlers.py     # Telegram subscription management
├── coupons/
│   ├── __init__.py
│   └── handlers.py     # Campaigns, broadcasts, templates
└── forex/
    ├── __init__.py
    └── handlers.py     # Signals, config, bot status
```

### Subscriptions Domain (`domains/subscriptions/handlers.py`)

Manages Telegram VIP channel access:

| Handler | Endpoint | Purpose |
|---------|----------|---------|
| `handle_telegram_check_access` | GET `/api/telegram/check-access/<email>` | Check if user has channel access |
| `handle_telegram_subscriptions` | GET `/api/telegram-subscriptions` | List all subscriptions |
| `handle_telegram_grant_access` | POST `/api/telegram/grant-access` | Create subscription, generate invite link |
| `handle_telegram_cancel_subscription` | POST `/api/telegram/cancel-subscription` | Cancel via Stripe, kick from channel |
| `handle_telegram_revenue_metrics` | GET `/api/telegram/revenue-metrics` | Stripe revenue aggregation |

Key pattern: Handlers import `server` module at runtime to access globals (`server.db`, `server.telegram_bot`).

### Coupons Domain (`domains/coupons/handlers.py`)

Campaign and template management:

| Handler | Purpose |
|---------|---------|
| `handle_campaigns_list` | List all campaigns |
| `handle_campaign_by_id` | Get single campaign |
| `handle_campaigns_create` | Create new campaign |
| `handle_validate_coupon` | Validate coupon code |
| `handle_broadcast` | Send message to bot users |
| `handle_upload_template` | Upload coupon template |

### Forex Domain (`domains/forex/handlers.py`)

Trading signal management:

| Handler | Purpose |
|---------|---------|
| `handle_forex_signals` | List signals with filters |
| `handle_forex_config` | Get/update trading parameters |
| `handle_signal_bot_status` | Current bot state, open signal, P&L |
| `handle_signal_bot_set_active` | Switch trading strategy |
| `handle_xauusd_sparkline` | Price chart data |

---

## 5. Integrations

### Stripe (`integrations/stripe/`)

**Webhook Handler**: `integrations/stripe/webhooks.py`

Handles Stripe events without session auth (uses signature verification):

```python
def handle_stripe_webhook(handler, stripe_available, telegram_bot_available, db_module):
    # Verify Stripe signature
    event, error = verify_webhook_signature(payload, sig_header, webhook_secret)
    
    # Handle events
    if event_type == 'checkout.session.completed':
        # Create subscription record
    elif event_type == 'customer.subscription.deleted':
        # Revoke access, kick from Telegram
    elif event_type == 'invoice.payment_failed':
        # Mark as failed, kick user, send notification
```

**Idempotency**: Events are tracked in `webhook_events_processed` table to prevent duplicate processing on retries.

**Client**: `stripe_client.py` wraps Stripe SDK operations.

### Telegram (`integrations/telegram/`)

**Two Bots**:
1. **Coupon Bot** (`TELEGRAM_BOT_TOKEN`): User commands for coupon validation
2. **Forex Bot** (`FOREX_BOT_TOKEN`): Signal delivery to channels

**Webhook Endpoints**:
- `POST /api/telegram-webhook` → Coupon bot updates
- `POST /api/forex-telegram-webhook` → Forex bot updates

**Handler Pattern**: Webhooks receive dependencies as parameters:

```python
def handle_coupon_telegram_webhook(handler, telegram_bot_available, telegram_bot_module):
    # Parse update from Telegram
    result = telegram_bot_module.handle_telegram_webhook(webhook_data, bot_token)
```

**Bot Implementation**: `telegram_bot.py` and `forex_bot.py` handle message parsing, command routing, and API calls.

### OpenAI (`integrations/openai/`)

Used for:
- Signal guidance messages
- TP/SL celebration text
- Daily/weekly recap generation

Client initialized via Replit's OpenAI integration (`AI_INTEGRATIONS_OPENAI_API_KEY`).

### Twelve Data (`integrations/market_data/`)

**Purpose**: Real-time XAU/USD price data for signal generation and monitoring.

```python
# In forex_api.py:
twelve_data_client.get_price("XAU/USD")
twelve_data_client.get_time_series(symbol='XAU/USD', interval='1min', outputsize=30)
```

Used by forex scheduler for:
- Signal generation (check indicators)
- Active signal monitoring (TP/SL tracking)
- Sparkline chart data

---

## 6. Workers & Background Jobs

### Worker Package Structure

```
workers/
├── __init__.py           # Re-exports for clean imports
├── scheduler.py          # Thin wrapper around forex_scheduler
├── price_monitor.py      # Wrapper around bots/core/price_monitor
└── milestone_tracker.py  # Wrapper around bots/core/milestone_tracker
```

**Why wrappers?** Clean import paths without modifying core implementations:

```python
# workers/scheduler.py
from forex_scheduler import start_forex_scheduler
__all__ = ['start_forex_scheduler']
```

### Forex Scheduler (`forex_scheduler.py`)

Main async loop with multiple tasks:

```python
class ForexScheduler:
    async def run_forever(self):
        while True:
            # Every 15 min: Check for new signals
            # Every 1 min: Monitor active signals for TP/SL
            # Every 1 min: Check milestone progress
            # Every 5 min: Revalidate stagnant signals
            # Scheduled: Daily/weekly recaps
```

**Signal Lifecycle**:
1. `run_signal_check()`: Generate new signals from technical analysis
2. `run_signal_monitoring()`: Track price vs TP/SL levels
3. `run_signal_guidance()`: Milestone notifications (40% to TP, breakeven alert, etc.)
4. `run_stagnant_signal_checks()`: Timeout signals after 4 hours

### Price Monitor (`bots/core/price_monitor.py`)

Singleton that tracks real-time price for active signals:
- Calculates current P&L in pips
- Detects TP/SL hits
- Provides data for status endpoints

### Milestone Tracker (`bots/core/milestone_tracker.py`)

Generates celebratory/warning messages at price milestones:
- 40% toward TP1: Motivational message
- 70% toward TP1: Breakeven alert
- TP1/TP2/TP3 hits: Celebration messages
- SL hit: Acknowledgment message

---

## 7. Configuration & Secrets

### Config Class (`core/config.py`)

Centralized environment variable access:

```python
class Config:
    @staticmethod
    def get_port():
        return int(os.environ.get('PORT', 5000))
    
    @staticmethod
    def get_stripe_secret_key():
        return os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_SECRET')
```

**Design principle**: No side effects at import time. Just reads env vars.

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `PORT` | HTTP server port (default 5000) |
| `ADMIN_PASSWORD` | Session signing secret |
| `DATABASE_URL` or `DB_HOST` | PostgreSQL connection |
| `TELEGRAM_BOT_TOKEN` | Coupon bot token |
| `FOREX_BOT_TOKEN` | Forex signal bot token |
| `FOREX_CHANNEL_ID` | VIP channel for signals |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification |
| `TWELVE_DATA_API_KEY` | Market data API |
| `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY` | Object storage |
| `ENTRYLAB_API_KEY` | External API auth |
| `REPLIT_DEPLOYMENT` | Production flag (`1` = prod) |

### Platform Config vs Runtime State

**Platform config** (in `forex_config` DB table):
- Trading hours, RSI thresholds, ATR multipliers
- TP count and percentages
- Session filter settings

**Runtime state** (in `bot_config` DB table):
- Active bot strategy
- Queued bot switch

The scheduler hot-reloads config changes by checking `updated_at` timestamps.

---

## 8. Current Limitations

### Single-Tenant Design

The entire system operates as a single tenant:
- One coupon bot, one forex bot
- One PostgreSQL database
- One Stripe account
- One VIP Telegram channel

There is no concept of multi-tenancy or isolated customer accounts.

### Global Singletons

Many modules use global state:

```python
# In db.py:
db_pool = DatabasePool()  # Global connection pool

# In telegram_bot.py:
bot = None  # Global bot instance

# In forex_scheduler.py:
forex_scheduler = ForexScheduler()  # Global scheduler
```

### Shared Database

All domains share the same database:
- `campaigns`, `campaign_submissions` (coupons)
- `forex_signals`, `forex_config`, `bot_config` (forex)
- `telegram_subscriptions`, `webhook_events_processed` (subscriptions)
- `bot_users`, `bot_usage_logs` (telegram)

### No Horizontal Scaling

- Single-process design prevents horizontal scaling
- Background scheduler assumes single instance
- No distributed locking for signal generation

### Process Restart State

On restart:
- Active signals resume monitoring (state in DB)
- Webhooks need re-registration
- Scheduler restarts fresh (no persistent task queue)

---

## 9. Safety Invariants

### 1. Import Must Not Start Side Effects

**Violation example (bad)**:
```python
# At module top level
db = connect_to_database()  # BAD: runs at import time
```

**Correct pattern**:
```python
# In create_app_context():
ctx.database_available = bool(os.environ.get('DATABASE_URL'))
# Actual connection happens in start_app()
```

### 2. Webhooks Register Only in Bootstrap

Telegram webhook URLs are set exactly once in `start_app()`:

```python
telegram_bot.start_webhook_bot(ctx.coupon_bot_token)
telegram_bot.setup_forex_webhook(ctx.forex_bot_token, webhook_url)
```

### 3. Scheduler Starts Once

Protected by `_started` flag:

```python
def start_app(ctx):
    global _started
    if _started:
        return
    _started = True
    # ... start scheduler
```

### 4. Middleware is the Auth/DB Gate

All protected endpoints must have `auth_required=True` or `db_required=True` in route definition:

```python
Route('GET', '/api/forex-signals', 'handle_api_forex_signals',
      auth_required=True, db_required=True)
```

Handlers **trust** that middleware has already validated access.

### 5. Webhook Handlers Return 200

Telegram and Stripe webhooks always return 200 to prevent retries:

```python
# Even on error:
handler.send_response(200)  # Telegram won't retry
handler.wfile.write(json.dumps({'error': str(e)}).encode())
```

Stripe webhooks use idempotency table to handle retries gracefully.

### 6. Single Active Signal Constraint

Forex scheduler enforces one signal at a time:

```python
pending_signals = get_forex_signals(status='pending')
if pending_signals:
    return  # Skip new signal generation
```

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **Handler** | Function that processes an HTTP request. Receives handler instance, reads request, writes response. |
| **Domain** | Business capability grouping (subscriptions, coupons, forex). Lives in `domains/` directory. |
| **Worker** | Background task/thread. Currently: forex scheduler, price monitor, milestone tracker. |
| **Middleware** | Code that runs before handlers to check auth/availability. In `api/middleware.py`. |
| **Integration** | External service connection (Stripe, Telegram, Twelve Data, OpenAI). |
| **Route** | Mapping of HTTP method + path to handler with metadata (auth required, etc). |
| **AppContext** | Dataclass holding availability flags and tokens. Created at startup. |
| **Bootstrap** | Process of starting side effects (DB, webhooks, scheduler). |
| **Signal** | Forex trading signal with entry, TP1/TP2/TP3, SL prices. |
| **Milestone** | Progress checkpoint for active signal (40% to TP, breakeven, etc). |
| **Bot Config** | Runtime state (active strategy). Hot-reloaded by scheduler. |
| **Forex Config** | Trading parameters (RSI, ATR, hours). Hot-reloaded by scheduler. |
| **Coupon Bot** | Telegram bot for coupon validation. |
| **Forex Bot** | Telegram bot for signal delivery to channels. |
| **VIP Channel** | Private Telegram channel for paying subscribers. |

---

## File Reference

| File | Purpose |
|------|---------|
| `server.py` | HTTP server entrypoint, request handler class |
| `core/config.py` | Environment variable access |
| `core/app_context.py` | Startup context creation |
| `core/bootstrap.py` | Side-effect initialization |
| `api/routes.py` | Route definitions |
| `api/middleware.py` | Auth/DB checks |
| `domains/*/handlers.py` | Business logic handlers |
| `integrations/*/webhooks.py` | Webhook handlers |
| `workers/*.py` | Background task wrappers |
| `forex_scheduler.py` | Main scheduler loop |
| `forex_signals.py` | Signal generation engine |
| `forex_bot.py` | Telegram signal delivery |
| `telegram_bot.py` | Coupon bot implementation |
| `stripe_client.py` | Stripe API wrapper |
| `db.py` | Database connection and queries |
