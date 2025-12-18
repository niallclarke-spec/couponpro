# PromoStack Promo Gen

## Documentation
For detailed technical documentation, see the `docs/` folder:
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture, request flow, directory structure
- **[docs/DATABASE.md](docs/DATABASE.md)** - Complete database schema reference with all tables
- **[docs/DOMAIN_MODULES.md](docs/DOMAIN_MODULES.md)** - Domain modules (Journeys, Connections, CrossPromo, Forex)
- **[docs/ENV_REFERENCE.md](docs/ENV_REFERENCE.md)** - All environment variables with descriptions
- **[docs/MULTI_TENANT_FOREX_ROADMAP.md](docs/MULTI_TENANT_FOREX_ROADMAP.md)** - Future multi-tenant forex scheduler design

## Overview
PromoStack is a platform designed for the rapid generation of branded promotional images, specifically coupons, for social media and messaging. It offers both a web application (dash.promostack.io) and a Telegram bot (@promostack_bot), aiming to streamline marketing asset creation. The platform also includes a Forex Signals Bot, showcasing a multi-bot architecture, with future plans for a multi-tenant SaaS Bot Hub marketplace.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform features a dark navy theme with a unified admin dashboard, employing a dual-sidebar layout for product switching and feature navigation. It utilizes hash-based routing for in-page navigation and is designed for mobile responsiveness with collapsible sidebars. The admin interface emphasizes intuitive workflows, real-time visual feedback, live previews, a drag-to-draw interface for text manipulation, high-DPI rendering, and color pickers. A consistent design system is enforced through CSS variables for colors and dimensions.

### Technical Implementations
The frontend is built with pure HTML, CSS, and vanilla JavaScript. The backend and API utilize a Python HTTP server (`server.py`). Client-side image generation occurs via canvas manipulation, while the Telegram bot employs server-side Python/Pillow for image rendering. Persistent storage for template images and `meta.json` backups is managed by Digital Ocean Spaces (S3-compatible) with CDN, using `boto3`.

### Dual-Subdomain Architecture
The system operates with `admin.promostack.io` for admin-only access and `dash.promostack.io` for client dashboards. Host-aware routing in `core/host_context.py` directs traffic and enforces access rules based on the subdomain.

### Tenant Onboarding System
New users accessing `dash.promostack.io` are guided through a 4-step setup wizard covering Telegram Bot setup, Stripe Configuration, and Business Information before accessing the main dashboard. The system auto-provisions new tenants and tracks onboarding state in the `onboarding_state` table.

### Authentication Architecture
The platform supports dual authentication: primary Clerk JWT authentication (via `Authorization: Bearer` headers and `X-Clerk-User-Email` header for email) and legacy HMAC-signed `admin_session` cookie authentication. Host-aware rules in `auth/clerk_auth.py` and `core/clerk_auth.py` define access levels for admin and client dashboards, with admin access requiring a whitelisted email.

**Clerk JWKS Configuration (Dec 2025 - Dynamic Issuer Mode)**:
- JWKS URL dynamically derived from each token's `iss` claim: `{token_iss}/.well-known/jwks.json`
- No environment variables required for JWKS configuration (fully automatic)
- Per-issuer PyJWKClient cache with thread-safe refresh-on-miss logic
- PyJWKClient caches keys for 30 minutes per issuer; refreshes once on kid mismatch before failing
- Optional `CLERK_ALLOWED_ISSUERS` env var for production security (comma-separated allowlist)
- Debug endpoint `/api/auth/debug` shows cached issuers, their JWKS URLs, key counts, and refresh times
- JWT doesn't include email directly; code falls back to `X-Clerk-User-Email` header or `clerk_user_email` cookie
- `/api/set-auth-cookie` returns 401 on auth failure, 403 on non-admin (not 200)

### Feature Specifications
- **Web Application**: Dynamic template loading, auto-fitting text, live previews, logo overlays, image download/share, and a password-protected admin panel.
- **Telegram Bot Integration**: Server-side rendering for promo images, posting to Telegram channels, and coupon validation via FunderPro API.
- **Campaigns & Promotions**: Admin-managed system for creating campaigns with visual overlays and user uploads, backed by PostgreSQL.
- **FunderPro CRM Integration**: Real-time coupon validation.
- **Telegram Broadcast System**: Admin feature for broadcasting messages to bot users.
- **Template Visibility Control**: Admin panel to manage template visibility for the Telegram bot.
- **Bot Analytics Dashboard**: Admin dashboard for tracking generations, users, success rates, and top templates.
- **Forex Signals Bot**: Automated XAU/USD (Gold) trading signals using multi-indicator strategies, dynamic TP/SL, AI-powered messages, and daily/weekly performance recaps.
- **Modular Strategy System (Forex Bot)**: Plug-and-play strategy architecture (`strategies/`) with a `base_strategy.py` interface and `strategy_loader.py`. Includes a Multi-TP System for phased profit taking.
- **Milestone Tracker System**: Unified system (`bots/core/milestone_tracker.py`) for sending signal progress notifications with AI-generated messages and P&L tracking.
- **Journeys System**: Event-triggered, multi-step conversational flows for Telegram bots via deep links, with linear flows and specific constraints on steps and delays. Database tables (`journeys`, `journey_steps`, `journey_user_sessions`, `journey_scheduled_messages`) store journey data, and `domains/journeys/engine.py` manages step execution. Frontend uses a shared module (`assets/js/journeys.js` + `assets/css/journeys.css`) initialized via `initJourneys()` that exposes all functions via `window.JourneysModule.*` namespace for both admin and client dashboards. Deep link URLs are displayed with copy/test buttons when a Message Bot is configured. **Webhook Flow**: `/api/bot-webhook/<secret>` receives Telegram updates, resolves tenant via `db.resolve_bot_connection_from_webhook_secret()`, and routes to journey trigger/reply handlers in `integrations/telegram/webhooks.py`. Journeys use `bot_id` matching the Message Bot's username for proper trigger detection. **Step Types**: `message` (send + advance), `question` (send + wait for reply), `delay` (schedule future message via scheduler), `wait_for_reply` (pause until reply or timeout). **Scheduler**: Background thread in `domains/journeys/scheduler.py` polls every 30s using `FOR UPDATE SKIP LOCKED` for idempotent processing of delayed messages and wait timeouts. Session statuses include `active`, `waiting_delay`, `awaiting_reply`, and `completed`.
- **Connections System**: Tenant-specific bot configuration for Signal Bot (forex signals) and Message Bot (user interactions/journeys). Stored in `tenant_bot_connections` table with bot tokens, channel IDs, webhook secrets, and auto-webhook setup. Handlers in `domains/connections/handlers.py` validate tokens via Telegram getMe API and configure webhooks. The Connections tab is the **single source of truth** for all bot credentials - there are no environment variable fallbacks.
- **BotCredentialResolver**: Centralized credential access service in `core/bot_credentials.py`. All bot systems (forex signals, webhooks, journeys) use `get_bot_credentials(tenant_id, bot_role)` exclusively. Raises `BotNotConfiguredError` with actionable messages when credentials are missing. Migration script `scripts/seed_entrylab_bots.py` available for one-time token seeding from environment variables.
- **Telegram Send Infrastructure (Dec 2025)**: Production-grade message sending via `core/telegram_sender.py`. Features: 60s TTL cache for bot connections (thread-safe), short-lived `telegram.Bot` instances per send (no cached bot objects), explicit cache invalidation when credentials saved/deleted in Connections UI, fail-fast behavior (no fallback bot - crisp errors when credentials missing), masked token logging (`****abcd`). All Telegram sends MUST go through `send_to_channel()` or `send_message()` - no direct telegram.Bot instantiation allowed. Endpoint `/api/connections/validate-saved` provides dry-run credential validation via Telegram API.
- **Cross Promo Automation**: Automated system for cross-promoting VIP signals in FREE channels. Domain-driven architecture in `domains/crosspromo/` with repo, service, and handlers layers. Features include: Mon-Fri only execution, scheduled jobs (09:00 morning news, 10:00 VIP teaser), Alpha Vantage gold news integration, winning signal copying with congratulations CTA, atomic job claiming using `FOR UPDATE SKIP LOCKED`, tenant-isolated settings storage in `tenant_crosspromo_settings` table, and job queue in `crosspromo_jobs` table. Telegram messaging prefers `copyMessage` over `forwardMessage` to avoid attribution. UI in admin.html under Forex product navigation.

### Server Architecture
The server employs a dispatcher pattern with thin request handlers (`server.py`), centralized routing in `api/dispatch.py` and `api/routes.py`, and middleware for authentication and database checks (`api/middleware.py`). This ensures a clean separation of concerns and maintainability.

### Repository Pattern (Dec 2025)
Domain-specific repository modules centralize database access with consistent error handling:
- **domains/connections/repo.py**: `list_connections()`, `get_connection()`, `upsert_connection()`, `delete_connection()`
- **domains/tenant/repo.py**: `tenant_exists()`, `upsert_integration()`, `map_user_to_tenant()`
- **domains/journeys/repo.py**: Journey-specific database operations
- **domains/crosspromo/repo.py**: Cross-promo job and settings operations

**Database Availability Pattern**: All repository functions use `_require_db_pool()` guard that raises `DatabaseUnavailableError` when `db.db_pool` is None. Handlers catch this exception and return consistent 503 responses with `{'error': 'Database not available'}`. This ensures:
- Fail-fast behavior when database is unavailable
- Consistent error responses across all API endpoints
- No silent failures or fallback data

### System Design Choices
Stateless HMAC-signed cookie authentication is used for ephemeral environments. Digital Ocean Spaces provides persistent storage for templates. The system uses a hybrid storage model, is modular, and configured via environment variables. Image generation for Telegram uses Pillow, and coupon validation is enforced at the API level. Production robustness for the Telegram bot includes `asyncio.to_thread()`, `AIORateLimiter`, and a single-process webhook architecture. Stripe API is the source of truth for revenue metrics.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage (`couponpro-templates`).
- **Digital Ocean PostgreSQL**: Managed database (`promostack-db`).
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime.
- **Python Packages**: `boto3`, `psycopg2-binary`, `Pillow`, `python-dotenv`, `python-telegram-bot[rate-limiter]`, `aiolimiter`.
- **Environment Secrets**: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `SPACES_ACCESS_KEY`, `ADMIN_PASSWORD`, `FUNDERPRO_PRODUCT_ID`, `FOREX_BOT_TOKEN`, `TWELVE_DATA_API_KEY`, etc.
- **.do/app.yaml**: Digital Ocean application configuration.