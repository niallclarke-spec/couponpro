# PromoStack Promo Gen

## Overview
PromoStack is a platform for the rapid generation of branded promotional images, specifically coupons, for social media and messaging. It offers a web application (dash.promostack.io) and a Telegram bot (@promostack_bot), streamlining marketing asset creation. The platform also features a Forex Signals Bot, showcasing a multi-bot architecture, with future plans for a multi-tenant SaaS Bot Hub marketplace.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform features a dark navy theme with a unified admin dashboard, employing a dual-sidebar layout for product switching and feature navigation. It utilizes hash-based routing, is designed for mobile responsiveness, and emphasizes intuitive workflows, real-time visual feedback, live previews, a drag-to-draw interface for text manipulation, high-DPI rendering, and color pickers. A consistent design system is enforced through CSS variables.

### Technical Implementations
The frontend is built with pure HTML, CSS, and vanilla JavaScript. The backend and API utilize a Python HTTP server. Client-side image generation occurs via canvas manipulation, while the Telegram bot employs server-side Python/Pillow for image rendering. Persistent storage for template images and `meta.json` backups is managed by Digital Ocean Spaces (S3-compatible) with CDN, using `boto3`.

### Dual-Subdomain Architecture
The system operates with `admin.promostack.io` for admin-only access and `dash.promostack.io` for client dashboards, with host-aware routing dictating access.

### Tenant Onboarding System
New users accessing `dash.promostack.io` are guided through a 4-step setup wizard, which auto-provisions new tenants and tracks onboarding state.

### Authentication Architecture
The platform supports dual authentication: primary Clerk JWT authentication and legacy HMAC-signed `admin_session` cookie authentication. Host-aware rules define access levels, with admin access requiring a whitelisted email. JWKS configuration for Clerk is dynamic, deriving the JWKS URL from the token's `iss` claim.

### Feature Specifications
- **Web Application**: Dynamic template loading, auto-fitting text, live previews, logo overlays, image download/share, and a password-protected admin panel.
- **Telegram Bot Integration**: Server-side rendering for promo images, posting to Telegram channels, and coupon validation.
- **Campaigns & Promotions**: Admin-managed system for creating campaigns with visual overlays and user uploads.
- **FunderPro CRM Integration**: Real-time coupon validation.
- **Telegram Broadcast System**: Admin feature for broadcasting messages.
- **Template Visibility Control**: Admin panel to manage template visibility for the Telegram bot.
- **Bot Analytics Dashboard**: Admin dashboard for tracking generations, users, and performance.
- **Forex Signals Bot**: Automated XAU/USD trading signals using multi-indicator strategies, dynamic TP/SL, AI-powered messages, and performance recaps. It features a modular strategy system and a centralized pip calculator.
- **Milestone Tracker System**: Unified system for sending signal progress notifications with AI-generated messages and P&L tracking.
- **Journeys System**: Event-triggered, multi-step conversational flows for Telegram bots via deep links or direct messages. It supports various step types (message, question, delay, wait_for_reply), a background scheduler (10s polling interval), and step analytics including link click tracking. Telethon user clients handle private messages. Personalised welcome messages (`welcome_message` column on journeys, `{first_name}` placeholder replaced with Telegram first name at trigger time). Inline execution for delays ≤15s (exact timing via sleep), deferred to scheduler for >15s. Production reliability features include: per-user async locking (LRU-evicting, max 1000), message deduplication via `journey_inbound_dedupe` table, session auto-heal (broken sessions marked and fall through to DM triggers), inactivity auto-complete (configurable `inactivity_timeout_days` per journey, enforced in both listener and scheduler), stale job guard (scheduler validates session status + step match before sending), journey priority (`priority_int` column, highest priority wins on trigger match), journey locking (`is_locked` prevents edits, duplicate endpoint clones journey+steps+triggers), and await-reply keyword branching (`branch_keyword`, `branch_true_step_id`, `branch_false_step_id` on journey_steps).
- **Journey Lifecycle**: Three states: Draft (editable, not triggering), Active (live, triggering for new users), Stopped (no new triggers, in-progress users finish). Publish endpoint validates no duplicate active trigger keywords (returns 409 on conflict). Duplicate creates a draft copy and prompts to stop the original. Journey cards show aggregate stats (total sends, unique users). set_steps safely deletes scheduled messages before steps to prevent FK violations.
- **Connections System**: Tenant-specific bot configuration for Signal Bot and User Account (Telethon), storing bot tokens, channel IDs, and webhook secrets. This is the single source of truth for bot credentials. Message Bot is removed from the UI. Connections page uses iOS-style single-column expandable accordion layout.
- **BotCredentialResolver**: Centralized service for accessing bot credentials, raising actionable errors when credentials are missing.
- **Telegram Send Infrastructure**: Production-grade message sending with a 60s TTL cache for bot connections, short-lived `telegram.Bot` instances, explicit cache invalidation, and fail-fast behavior.
- **Telethon User Client**: Telegram User API integration for Journey messaging without bot labels, featuring a singleton client per tenant, rate limiting, and session persistence.
- **Cross Promo Automation**: Automated system for cross-promoting VIP signals in FREE channels, including scheduled jobs, Alpha Vantage gold news integration, and atomic job claiming. Morning sequence posts three timed messages to FREE channel (morning news, weekly recap forward if available, VIP teaser) at configurable UTC times (default 06:42, 07:12, 07:51). Weekly recap message IDs are tracked so they can be forwarded from VIP to FREE. End-of-day pip brag at 20:00 UTC. Cross Promo settings are embedded within the Signal Bot connection card on the Connections page (no standalone page).
- **Hype Chat Bot**: AI-powered motivational messaging for FREE channel. Uses OpenAI (gpt-4o-mini) with a fixed EntryLab system prompt and auto-injected pip performance context (today + 7-day). Admin creates named Prompts (custom instructions for message angle/style) and Flows (scheduling rules: message count, interval between messages, delay after CTA, active days). Triggers automatically after CTA message, once per day, with deduplication. Messages are scheduled as crosspromo_jobs with staggered run_at times. Admin UI at `#forex/hype-bot` with prompt CRUD, flow CRUD, preview (generate without sending), manual trigger, and per-flow analytics. Domain: `domains/hypechat/` (repo, service, handlers).
- **Navigation Restructure**: Journeys sidebar item split into parent group "Journeys" with two children: "Support Chat" (existing DM journey flows) and "Hype Bot" (new channel posting system). Legacy `#forex/journeys` hash redirects to `#forex/support-chat`.

### Server Architecture
The server employs a dispatcher pattern with thin request handlers, centralized routing, and middleware for authentication and database checks. **Leader Lock (PostgreSQL advisory lock)** gates ALL background workers (Forex scheduler, Journey scheduler, Cross Promo worker, Telethon listener) so only one instance runs them in multi-instance deployments. Standby instances handle webhooks/API requests but do not run scheduled jobs. Leader retry loop checks every 10s for failover.

### Repository Pattern
Domain-specific repository modules centralize database access with consistent error handling, implementing a `Database Availability Pattern` (raising 503 on unavailability) and a `Tenant Isolation Pattern` (rejecting requests without valid tenant context).

### System Design Choices
Stateless HMAC-signed cookie authentication is used. Digital Ocean Spaces provides persistent storage. The system uses a hybrid storage model, is modular, and configured via environment variables. Image generation for Telegram uses Pillow, and coupon validation is enforced at the API level. Production robustness for the Telegram bot includes `asyncio.to_thread()`, `AIORateLimiter`, and a single-process webhook architecture. Stripe API is the source of truth for revenue metrics.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage.
- **Digital Ocean PostgreSQL**: Managed database.
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime.
- **Python Packages**: `boto3`, `psycopg2-binary`, `Pillow`, `python-dotenv`, `python-telegram-bot[rate-limiter]`, `aiolimiter`, `telethon`, `cryptg`.
- **Environment Secrets**: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `SPACES_ACCESS_KEY`, `ADMIN_PASSWORD`, `FUNDERPRO_PRODUCT_ID`, `FOREX_BOT_TOKEN`, `TWELVE_DATA_API_KEY`, etc.
- **.do/app.yaml**: Digital Ocean application configuration.