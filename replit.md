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

### Modular Strategy System (Forex Bot)
The forex signals bot uses a modular strategy architecture (`strategies/`) that enables plug-and-play bot strategies:

**Architecture:**
- `strategies/base_strategy.py`: Abstract base class defining the strategy interface
- `strategies/aggressive.py`: Aggressive strategy with wider RSI thresholds (40/60)
- `strategies/conservative.py`: Conservative strategy with tighter thresholds (35/65)
- `strategies/raja_banks.py`: Raja Banks Gold Start strategy with session-based impulse breakouts
- `strategies/strategy_loader.py`: Registry and factory for loading strategies
- `forex_signals.py`: Delegates to active strategy; owns shared monitoring/guidance logic

**Raja Banks Gold Start Strategy:**
- Session-based trading: London (07:00-10:00 UTC), New York (12:00-16:00 UTC), Overlap (13:00-16:00 UTC)
- 15-minute impulse candle breakout detection
- Maximum 4 signals per day with 15-minute cooldown between signals
- Hybrid trend filter: Trades with EMA 50/200 trend, allows counter-trend at clear S/R zones
- Tight stop-loss: Just below candle low (BUY) or above candle high (SELL)
- Wick fill targeting: Primary TP at previous candle's wick, secondary TP at ATR extension
- Uses database persistence for daily signal counts (survives server restarts)

**Multi-TP System:**
- TP1: 50% position close at first target
- TP2: 30% position close at second target  
- TP3: 20% position close at final target
- Breakeven alert at 70% progress toward TP1

**To add a new strategy (2 files only):**

1. **Create strategy file**: `strategies/your_strategy.py`
   - Copy from `strategies/aggressive.py` as template
   - Set unique `bot_type = "your_bot_name"` (this is the database key)
   - Set `name` and `description` for admin UI display
   - Implement required methods: `check_for_signals()`, `calculate_tp_sl()`
   - Optional: `validate_thesis()`, `get_indicators_used()`

2. **Register in loader**: `strategies/strategy_loader.py` (add 2 lines)
   ```python
   from strategies.your_strategy import YourStrategy
   register_strategy(YourStrategy)
   ```

That's it! The admin UI automatically picks up new strategies from the registry.

**Active strategy** is stored in `bot_config` table as `active_bot` (read via `get_active_bot()` in db.py).

**IMPORTANT**: Strategy classes only control signal generation logic. All post-signal behavior is shared.

### Shared Logic Files (Same for ALL Bots)
These files handle shared functionality that works identically regardless of which bot generated the signal:

| Feature | File | Notes |
|---------|------|-------|
| Daily Recap | `forex_bot.py` | `post_daily_recap()` - Morning recap of yesterday's signals |
| Weekly Recap | `forex_bot.py` | `post_weekly_recap()` - Sunday performance summary |
| Milestone Tracker | `bots/core/milestone_tracker.py` | Unified notification system for all signal milestones |
| Price Monitoring | `bots/core/price_monitor.py` | TP/SL hit detection, 1-min checks |
| Signal Scheduling | `forex_scheduler.py` | Signal lifecycle, closing, monitoring |
| Guidance System | `forex_signals.py` | Progress updates, thesis validation |

### Milestone Tracker System
The unified milestone notification system (`bots/core/milestone_tracker.py`) handles all signal progress notifications:

**Milestones (in order):**
1. **40% toward TP1**: AI-generated motivational message
2. **70% toward TP1**: Celebration + breakeven advice (move SL to entry)
3. **TP1 Hit**: Celebration with pips gained, remaining position info
4. **50% toward TP2**: Small encouragement (if multi-TP)
5. **TP2 Hit**: Celebration + advice to move SL to TP1 (if 3-TP)
6. **TP3 Hit**: BIG celebration with emojis for full exit
7. **60% toward SL**: Calm warning message (one-time)
8. **SL Hit**: Professional loss message with accountability

**Key Features:**
- 90-second global cooldown between all messages
- AI-generated unique messages via Replit AI Integrations (gpt-5)
- Fallback messages if AI unavailable
- Database tracking via `milestones_sent` JSONB column
- Prevents duplicate notifications

**Database Columns (forex_signals):**
- `last_milestone_at`: Timestamp of last milestone message sent
- `milestones_sent`: JSONB tracking which milestones sent (40_percent, 70_percent, tp1_hit, etc.)

**Queued Bot Switching:**
When a signal is active, users can queue a different bot strategy. The queued bot will automatically activate when the current signal closes (won/lost/expired). This allows planning ahead without waiting for signals to complete.
- `queued_bot` stored in `bot_config` table
- Admin UI shows queued status with cancel option
- Automatic promotion triggers strategy reload in scheduler

### Indicator Configuration (Forex Bot)
The indicator system uses a centralized configuration in `indicator_config.py`. This ensures signal generation and thesis re-validation stay in sync when indicators change.

**To add a new indicator:**
1. Add an entry to `INDICATOR_REGISTRY` in `indicator_config.py` with:
   - `enabled`: True/False to toggle
   - `signal_logic`: Buy/sell conditions for signal generation
   - `validation_logic`: Weakening/broken rules for thesis re-validation
   - `display`: Formatting for messages
2. The thesis validator (`validate_thesis()`) and indicator storage automatically use the new indicator
3. AI messages automatically include the indicator in status updates via the reasons list

**To remove/disable an indicator:**
Set `'enabled': False` in the registry entry. Both signal generation and validation will skip it.

**Original indicators are stored** in the `original_indicators_json` JSONB column for dynamic future-proof storage.

### Forex Bot Timing Configuration
Timing constants are defined in `forex_signals.py` and `forex_scheduler.py` for easy configuration:

**Scheduler Intervals (forex_scheduler.py):**
- `SIGNAL_CHECK_INTERVAL`: 900s (15min) - Check for new signals
- `MONITOR_INTERVAL`: 300s (5min) - Monitor for TP/SL hits
- `GUIDANCE_INTERVAL`: 300s (5min) - Check guidance updates
- `STAGNANT_CHECK_INTERVAL`: 300s (5min) - Check stagnant signals

**Morning Schedule (forex_scheduler.py):**
- 6:20 AM UTC: Morning briefing with Alpha Vantage news and current gold price
- 6:30 AM UTC: Daily recap (yesterday's signals)
- 6:30 AM UTC Sunday: Weekly recap
- 7:00 AM UTC: Trading session opens (first signal checks)

**Signal Lifecycle (forex_signals.py):**
- `FIRST_REVALIDATION_MINUTES`: 90min - First thesis re-check
- `REVALIDATION_INTERVAL_MINUTES`: 30min - Subsequent re-checks
- `HARD_TIMEOUT_MINUTES`: 180min (3hr) - Close advisory

**Guidance Zones (forex_signals.py):**
- `PROGRESS_ZONE_THRESHOLD`: 30% - First progress update
- `BREAKEVEN_ZONE_THRESHOLD`: 60% - Breakeven advisory
- `DECISION_ZONE_THRESHOLD`: 85% - Final push update
- `GUIDANCE_COOLDOWN_MINUTES`: 10min - Minimum between messages

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