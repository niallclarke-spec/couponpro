# PromoStack Promo Gen

## Overview
PromoStack is a platform for rapid generation of branded promotional images, primarily coupons, for social media and messaging. It features a web application (dash.promostack.io) and a Telegram bot (@promostack_bot). The platform aims to streamline marketing asset creation and includes a Forex Signals Bot to demonstrate a multi-bot architecture, with future ambitions for a multi-tenant SaaS Bot Hub marketplace.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform uses a dark navy theme with a unified admin dashboard featuring a dual-sidebar layout (product switcher and feature navigation). It uses hash-based routing for in-page navigation and ensures mobile responsiveness with collapsible sidebars. The admin interface emphasizes intuitive workflows, real-time visual feedback, live previews, a drag-to-draw interface for text, high-DPI rendering, and color pickers.

**Design System:**
- Consistent CSS variables for colors (e.g., `--bg-primary`: #081028, `--accent-primary`: #CB3CFF) and dimensions (e.g., `--radius-sm/md/lg`).

### Technical Implementations
The frontend is built with pure HTML, CSS, and vanilla JavaScript. The backend and API are a Python HTTP server (`server.py`). Client-side image generation uses canvas manipulation for the web app, while the Telegram bot uses server-side Python/Pillow. Authentication is based on HMAC-signed cookie authentication for stateless sessions. Persistent storage for template images and `meta.json` backups is managed by Digital Ocean Spaces (S3-compatible) with CDN, utilizing `boto3`.

### Feature Specifications
- **Web Application**: Dynamic template loading, auto-fitting text, live previews, logo overlays, image download/share, and a password-protected admin panel for template management.
- **Telegram Bot Integration**: Generates and posts promo images to Telegram channels using server-side rendering, including coupon validation via FunderPro API.
- **Campaigns & Promotions**: Admin-managed system for creating promotional campaigns with visual overlays, user image uploads, and social media URL submission, backed by PostgreSQL.
- **FunderPro CRM Integration**: Real-time coupon validation against FunderPro's discount API.
- **Telegram Broadcast System**: Admin feature for broadcasting messages to bot users with rate limiting.
- **Template Visibility Control**: Admin panel to toggle template visibility for the Telegram bot.
- **Bot Analytics Dashboard**: Admin dashboard with smart chart switching for tracking generations, unique users, success rates, and top templates.
- **Forex Signals Bot**: Automated XAU/USD (Gold) trading signals based on multi-indicator strategies (EMA, ADX, RSI, MACD, Bollinger Bands, Stochastic Oscillator). Features ATR-based dynamic TP/SL, AI-powered messages, and daily/weekly performance recaps.

### Modular Strategy System (Forex Bot)
The Forex bot uses a modular strategy architecture (`strategies/`) allowing plug-and-play strategies. `base_strategy.py` defines the interface, and specific strategies (e.g., `aggressive.py`, `conservative.py`, `raja_banks.py`) implement it. A `strategy_loader.py` registers and loads strategies, with `forex_signals.py` delegating to the active strategy.
- **Raja Banks Gold Start Strategy**: Session-based trading, 15-minute impulse candle breakout detection, max 4 signals/day, hybrid trend filter, tight stop-loss, wick fill targeting, and database persistence.
- **Multi-TP System**: Phased profit taking at TP1 (50%), TP2 (30%), and TP3 (20%) with breakeven alerts.
- **Adding New Strategies**: Involves creating a new strategy file and registering it in `strategy_loader.py`.

### Shared Logic Files (Forex Bot)
Common functionalities shared across all Forex bot strategies include daily/weekly recaps, a unified milestone tracker, price monitoring for TP/SL hits, signal scheduling, and guidance systems for progress updates.

### Milestone Tracker System
A unified system (`bots/core/milestone_tracker.py`) sends notifications for signal progress (e.g., 40% toward TP1, TP1 Hit, SL Hit).
- Features: 90-second global cooldown, AI-generated messages via Replit AI Integrations (gpt-5), database tracking, and prevention of duplicate notifications.
- **P&L Tracking**: Uses `effective_sl` for realistic profit/loss calculation based on guided stop-loss movements.

### Indicator Configuration (Forex Bot)
Indicators are centrally configured in `indicator_config.py` with `enabled`, `signal_logic`, `validation_logic`, and `display` properties. This ensures consistency between signal generation and thesis re-validation.

### Forex Bot Timing Configuration
Timing constants for scheduler intervals (e.g., `SIGNAL_CHECK_INTERVAL`: 15min), morning schedule (e.g., 6:20 AM UTC briefing), signal lifecycle (e.g., `HARD_TIMEOUT_MINUTES`: 180min), and guidance zones are defined in `forex_signals.py` and `forex_scheduler.py`.

### System Design Choices
Stateless HMAC-signed cookie authentication is used for ephemeral environments. Digital Ocean Spaces serves as the primary persistent storage for templates. The system employs a hybrid storage model with local `meta.json` and object storage backups. The architecture is modular and configured via environment variables. Telegram image generation uses Pillow. Coupon validation is enforced at the API level. Production robustness for the Telegram bot includes `asyncio.to_thread()`, `AIORateLimiter`, and a single-process webhook architecture. Stripe API is the source of truth for revenue metrics.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage for `couponpro-templates`.
- **Digital Ocean PostgreSQL**: Managed database (`promostack-db`).
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime.
- **Python Packages**: `boto3`, `psycopg2-binary`, `Pillow`, `python-dotenv`, `python-telegram-bot[rate-limiter]`, `aiolimiter`.
- **Environment Secrets**: `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `SPACES_ACCESS_KEY`, `ADMIN_PASSWORD`, `FUNDERPRO_PRODUCT_ID`, `FOREX_BOT_TOKEN`, `TWELVE_DATA_API_KEY`, and others.
- **.do/app.yaml**: Digital Ocean application configuration.