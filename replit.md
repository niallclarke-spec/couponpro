# PromoStack Promo Gen

## Overview
PromoStack is a platform designed for the rapid generation of branded promotional images, primarily coupons, for marketing across social media and messaging platforms. It offers both a web application (dash.promostack.io) and a Telegram bot interface (@promostack_bot), streamlining the creation of visually appealing marketing assets. The platform also includes a Forex Signals Bot to prove a multi-bot architecture, with ambitions for a multi-tenant SaaS Bot Hub marketplace.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform employs a consistent dark theme. The unified admin dashboard features a dual-sidebar layout: a 60px product switcher with custom SVG icons and a 240px feature navigation sidebar. Hash-based routing provides smooth, in-page navigation. Mobile responsiveness is achieved through collapsible overlay sidebars. The admin interface emphasizes intuitive workflows with real-time visual feedback, live previews, and a drag-to-draw interface for text areas on coupons, supporting high-DPI rendering and color pickers.

### Technical Implementations
The frontend uses pure HTML, CSS, and vanilla JavaScript. The backend, including the admin panel and API, is a Python HTTP server (`server.py`). Client-side image generation is handled via canvas manipulation for the web app, while the Telegram bot utilizes server-side Python/Pillow for rendering. Authentication relies on HMAC-signed cookie authentication for stateless sessions. Persistent storage for template images and `meta.json` backups is managed by Digital Ocean Spaces (S3-compatible object storage) with CDN, accessed using `boto3`.

### Feature Specifications
- **Web Application**: Dynamic template loading, auto-fitting text, live previews, logo overlays, image download/share, and a password-protected admin panel for template management.
- **Telegram Bot Integration**: Processes commands to generate and post promo images directly to Telegram channels using server-side rendering, including coupon validation via FunderPro API.
- **Campaigns & Promotions**: Admin-managed system for creating promotional campaigns with visual overlays. Users participate via dedicated web pages, uploading images for compositing and submitting social media URLs. Uses PostgreSQL for data.
- **FunderPro CRM Integration**: Real-time coupon validation against FunderPro's discount API, ensuring only active and valid coupon codes are used for image generation.
- **Telegram Broadcast System**: Admin feature for broadcasting messages to active bot users, with rate limiting and graceful handling of blocked users.
- **Template Visibility Control**: Admin panel allows toggling template visibility specifically for the Telegram bot, updating `meta.json` and `index.json` accordingly.
- **Bot Analytics Dashboard**: Provides comprehensive admin analytics with smart chart switching (hourly/daily aggregation), tracking generations, unique users, success rates, top templates, and searchable coupon codes.
- **Forex Signals Bot**: Automated XAU/USD (Gold) trading signals based on a multi-indicator strategy (EMA, ADX, RSI, MACD, Bollinger Bands, Stochastic Oscillator), posted to a private Telegram channel. Features ATR-based dynamic TP/SL, AI-powered celebration messages, and daily/weekly performance recaps.

### System Design Choices
The system uses stateless HMAC-signed cookie authentication for ephemeral environments. Digital Ocean Spaces serves as the persistent storage for all template images, acting as the single source of truth. A hybrid storage model combines local `meta.json` files with object storage backups. The architecture is modular, configured via environment variables. Telegram image generation uses Pillow for high-quality rendering. Coupon validation is enforced at the API level. Production robustness for the Telegram bot includes `asyncio.to_thread()` for database calls, `AIORateLimiter` for Telegram API, and a single-process webhook architecture to maintain consistent state. Stripe API is the single source of truth for revenue metrics, using cached calls, subscription ID filtering, rebill calculations, and idempotent webhook handlers.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage for persistent template images (`couponpro-templates` bucket).
- **Digital Ocean PostgreSQL**: Managed database for campaigns and submissions (`promostack-db`).
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime environment.
- **`requirements.txt`**: Key Python packages include `boto3`, `psycopg2-binary`, `Pillow`, `python-dotenv`, `python-telegram-bot[rate-limiter]`, and `aiolimiter`.
- **Environment Secrets**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN_TEST`, `DATABASE_URL`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`, `ADMIN_PASSWORD`, `FUNDERPRO_PRODUCT_ID`, `FOREX_BOT_TOKEN`, `FOREX_CHANNEL_ID`, `TWELVE_DATA_API_KEY`.
- **.do/app.yaml**: Digital Ocean specific application configuration.