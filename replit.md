# PromoStack Promo Gen

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
- **Journeys System**: Event-triggered, multi-step conversational flows for Telegram bots via deep links, with linear flows and specific constraints on steps and delays. Database tables (`journeys`, `journey_steps`, `journey_user_sessions`, etc.) store journey data, and `domains/journeys/engine.py` manages step execution.

### Server Architecture
The server employs a dispatcher pattern with thin request handlers (`server.py`), centralized routing in `api/dispatch.py` and `api/routes.py`, and middleware for authentication and database checks (`api/middleware.py`). This ensures a clean separation of concerns and maintainability.

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