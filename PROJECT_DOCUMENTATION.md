# PromoStack/EntryLab - Complete Project Documentation

> **Purpose**: This document provides a comprehensive overview of the PromoStack platform for developers, AI assistants, and stakeholders who need to understand the codebase structure, features, and architecture.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [File Structure & Responsibilities](#3-file-structure--responsibilities)
4. [Database Schema](#4-database-schema)
5. [Key Features](#5-key-features)
6. [API Endpoints](#6-api-endpoints)
7. [Environment Variables](#7-environment-variables)
8. [Forex Signals System Deep Dive](#8-forex-signals-system-deep-dive)
9. [Subscription & Billing System](#9-subscription--billing-system)
10. [Admin Dashboard](#10-admin-dashboard)
11. [Architectural Health & Technical Debt](#11-architectural-health--technical-debt)
12. [Deployment](#12-deployment)

---

## 1. Project Overview

**PromoStack** is a multi-product platform consisting of two main products:

### Product 1: Coupon Bot
A promotional image generator for creating branded coupons and marketing assets for social media and messaging platforms.

- **Web App**: Public-facing coupon generator at `dash.promostack.io`
- **Telegram Bot**: @promostack_bot for generating coupons via chat
- **Admin Panel**: Template management, analytics, broadcast messaging

### Product 2: Forex Signals Bot (EntryLab)
An automated XAU/USD (Gold) trading signals service with freemium subscription model.

- **Free Channel**: Public Telegram channel with delayed signals
- **VIP Channel**: Private channel with real-time signals for paid subscribers
- **Subscription**: Stripe-powered weekly ($34.99) and monthly ($49) plans
- **Automation**: AI-powered signal generation, milestone tracking, performance recaps

### Access Points
| Platform | URL/Handle | Purpose |
|----------|------------|---------|
| Web Dashboard | `dash.promostack.io` | Admin panel for both products |
| Coupon Bot | @promostack_bot | Telegram bot for coupon generation |
| Forex Bot | @entrylabs | Telegram bot for trading signals |
| Landing Page | EntryLab frontend (separate repo) | Subscription checkout |

---

## 2. Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| **Backend** | Python 3.11 | Custom HTTP server (no framework like Flask/Django) |
| **Frontend** | HTML/CSS/JavaScript | Vanilla JS, no React/Vue - single-page app with hash routing |
| **Database** | PostgreSQL | Digital Ocean managed database |
| **Object Storage** | Digital Ocean Spaces | S3-compatible, used for template images |
| **Payments** | Stripe | Subscriptions, webhooks, revenue tracking |
| **Messaging** | Telegram Bot API | python-telegram-bot library with rate limiting |
| **AI** | OpenAI GPT | Signal messages, guidance, recaps via Replit AI integration |
| **Market Data** | Twelve Data API | Real-time XAU/USD price feed |
| **Image Generation** | Pillow (PIL) | Server-side coupon image rendering |
| **Deployment** | Digital Ocean App Platform | Production hosting |
| **Dev Environment** | Replit | Development and staging |

---

## 3. File Structure & Responsibilities

### Directory Structure
```
promostack/
├── server.py              # Main HTTP server (3,663 lines)
├── db.py                  # Database operations (4,786 lines)
├── stripe_client.py       # Stripe API wrapper (1,109 lines)
├── admin.html             # Admin dashboard SPA (9,290 lines)
├── index.html             # Public coupon generator
├── campaign.html          # Campaign submission page
│
├── telegram_bot.py        # Coupon bot logic
├── telegram_image_gen.py  # Pillow image generation
│
├── forex_bot.py           # Forex bot initialization
├── forex_signals.py       # Signal generation logic
├── forex_scheduler.py     # Background task scheduler
├── forex_ai.py            # AI message generation
├── forex_api.py           # Market data fetching
├── indicator_config.py    # Indicator settings
│
├── strategies/            # Modular trading strategies
│   ├── base_strategy.py   # Abstract base class
│   ├── raja_banks.py      # Primary strategy
│   ├── aggressive.py      # High risk variant
│   ├── conservative.py    # Low risk variant
│   └── strategy_loader.py # Dynamic loading
│
├── bots/core/             # Shared bot modules
│   ├── milestone_tracker.py  # TP/SL notifications
│   ├── price_monitor.py      # Real-time monitoring
│   ├── scheduler.py          # Async scheduler
│   └── ai_guidance.py        # Guidance messages
│
├── coupon_validator.py    # FunderPro API integration
├── object_storage.py      # DO Spaces wrapper
├── requirements.txt       # Python dependencies
└── .do/app.yaml          # DO deployment config
```

### Core Files Explained

#### `server.py` (3,663 lines)
The monolithic HTTP server handling:
- URL routing and request handling
- HMAC-signed cookie authentication
- Stripe webhook processing
- Telegram webhook endpoints
- Bot initialization and startup
- All API endpoints

#### `db.py` (4,786 lines)
Database layer including:
- Connection pooling with psycopg2
- Schema initialization (CREATE TABLE statements)
- Ad-hoc migrations at startup
- All CRUD operations as functions
- No ORM - raw SQL queries

#### `stripe_client.py` (1,109 lines)
Stripe integration:
- Revenue metrics calculation
- Subscription management
- Rebill forecasting
- Response caching (2-minute TTL)
- Churn rate calculation

#### `admin.html` (9,290 lines)
Single-page admin dashboard:
- HTML structure
- CSS styles (dark navy theme)
- JavaScript application logic
- Hash-based routing (#product/view)
- All admin UI components

---

## 4. Database Schema

### Tables Overview

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `campaigns` | Marketing campaigns | id, name, slug, overlay_image, active |
| `submissions` | User campaign submissions | id, campaign_id, image_url, social_url |
| `bot_usage` | Telegram analytics | id, user_id, template, success, error_type |
| `bot_users` | Telegram user profiles | id, telegram_id, username, first_name |
| `broadcast_jobs` | Admin message queue | id, message, status, sent_count |
| `forex_signals` | Trading signals | id, direction, entry, TP1/2/3, SL, status |
| `bot_config` | Bot settings | key, value (JSON) |
| `forex_config` | Strategy parameters | key, value (thresholds, multipliers) |
| `signal_narrative` | AI narratives | signal_id, narrative_text |
| `recent_phrases` | AI deduplication | phrase, created_at |
| `telegram_subscriptions` | VIP subscribers | id, email, stripe_id, telegram_username |
| `processed_webhook_events` | Webhook idempotency | event_id, processed_at |

### forex_signals Table (Critical)
```sql
CREATE TABLE forex_signals (
    id SERIAL PRIMARY KEY,
    direction VARCHAR(4),           -- 'BUY' or 'SELL'
    entry_price DECIMAL(10,5),
    stop_loss DECIMAL(10,5),
    take_profit_1 DECIMAL(10,5),
    take_profit_2 DECIMAL(10,5),
    take_profit_3 DECIMAL(10,5),
    status VARCHAR(20),             -- active, tp1_hit, tp2_hit, closed_tp, closed_sl, expired
    effective_sl DECIMAL(10,5),     -- Actual SL for P&L (moves with breakeven)
    breakeven_set BOOLEAN,
    breakeven_price DECIMAL(10,5),
    guidance_count INTEGER,
    last_guidance_at TIMESTAMP,
    indicators_used TEXT,           -- JSON of indicators that triggered
    notes TEXT,
    bot_type VARCHAR(50),
    telegram_message_id BIGINT,
    created_at TIMESTAMP,
    closed_at TIMESTAMP,
    close_price DECIMAL(10,5)
);
```

### telegram_subscriptions Table
```sql
CREATE TABLE telegram_subscriptions (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    name VARCHAR(255),
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

## 5. Key Features

### Coupon Bot Features
- **Template Management**: Upload/manage promotional templates
- **Dynamic Text Positioning**: Drag-to-draw coupon code placement
- **Auto-Fit Text**: Automatic text sizing for coupon codes
- **Logo Overlays**: Brand logo placement
- **FunderPro Validation**: Real-time coupon code validation
- **Telegram Generation**: Generate coupons via bot commands
- **Broadcast System**: Send messages to all bot users

### Forex Signals Bot Features

#### Signal Generation
- **Multi-Indicator Strategy**: EMA, ADX, RSI, MACD, Bollinger Bands, Stochastic
- **Session-Based Trading**: 8AM-10PM GMT trading hours
- **Impulse Candle Detection**: Raja Banks breakout strategy
- **Max 4 Signals/Day**: Rate limiting per strategy

#### Position Management
- **Multi-TP System**:
  - TP1: 50% of position
  - TP2: 30% of position
  - TP3: 20% of position
- **70% Breakeven Trigger**: Auto-move SL to entry at 70% toward TP1
- **3-Hour Hard Timeout**: Auto-expire stale signals

#### Monitoring & Notifications
- **1-Minute Price Monitoring**: Real-time TP/SL detection
- **Milestone Notifications**: Progress updates at 40%, 70%, TP hits
- **90-Second Cooldown**: Prevent notification spam
- **AI-Generated Messages**: GPT-powered announcements

#### Recaps & Briefings
- **Morning Briefing**: 6:20 AM UTC market outlook
- **Daily Recap**: 6:30 AM UTC performance summary
- **Weekly Recap**: Sunday performance summary
- **P&L Tracking**: Using effective_sl for accurate calculations

---

## 6. API Endpoints

### Authentication
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/login` | Admin login (password) |
| POST | `/api/logout` | Clear session |
| GET | `/api/check-auth` | Verify session |

### Coupon Bot
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/validate-coupon` | FunderPro validation |
| POST | `/api/upload-template` | Upload template (auth) |
| POST | `/api/delete-template` | Delete template (auth) |
| GET | `/api/campaigns` | List campaigns |
| POST | `/api/telegram-webhook` | Bot webhook |

### Forex Bot
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/forex-signals` | List signals (auth) |
| GET | `/api/forex-stats` | Performance stats (auth) |
| GET | `/api/forex-config` | Strategy config (auth) |
| POST | `/api/forex-config` | Update config (auth) |
| GET | `/api/signal-bot/status` | Bot status (auth) |
| POST | `/api/forex-telegram-webhook` | Bot webhook |

### Subscriptions
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/telegram-subscriptions` | List subscribers (auth) |
| POST | `/api/telegram/revoke-access` | Revoke VIP access (auth) |
| GET | `/api/telegram/revenue-metrics` | Stripe metrics (auth) |
| GET | `/api/telegram/billing/{id}` | Billing history (auth) |
| GET | `/api/telegram/conversion-analytics` | Conversion data (auth) |
| POST | `/api/stripe/webhook` | Stripe webhook |

---

## 7. Environment Variables

### Required for Production
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# Telegram
TELEGRAM_BOT_TOKEN=xxx          # Coupon bot
FOREX_BOT_TOKEN=xxx             # Forex bot (production)

# Stripe
STRIPE_SECRET_KEY=sk_live_xxx   # Live key for production
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Admin
ADMIN_PASSWORD=xxx

# Storage
SPACES_ACCESS_KEY=xxx
SPACES_SECRET_KEY=xxx
SPACES_BUCKET=couponpro-templates
SPACES_REGION=nyc3

# Market Data
TWELVE_DATA_API_KEY=xxx

# Coupon Validation
FUNDERPRO_PRODUCT_ID=xxx
```

### Development/Test
```bash
ENTRYLAB_TEST_BOT=xxx           # Test bot token (dev)
# Stripe test keys automatically detected by sk_test_ prefix
```

---

## 8. Forex Signals System Deep Dive

### Signal Lifecycle
```
1. GENERATE → Check indicators, create signal
2. ACTIVE → Monitor price every 1 minute
3. GUIDANCE → Send progress updates (40%, 70%)
4. BREAKEVEN → Move SL to entry at 70%
5. TP1_HIT → First target hit, 50% closed
6. TP2_HIT → Second target hit, 30% closed
7. CLOSED_TP/SL/EXPIRED → Final state
```

### Strategy Architecture
```python
# base_strategy.py
class BaseStrategy:
    def should_generate_signal(self, market_data) -> bool
    def calculate_entry(self, market_data) -> float
    def calculate_tp_levels(self, entry, direction) -> tuple
    def calculate_stop_loss(self, entry, direction) -> float

# raja_banks.py (Primary Strategy)
class RajaBanksStrategy(BaseStrategy):
    # Session-based: 8AM-10PM GMT
    # 15-minute impulse candle breakout
    # Max 4 signals per day
    # Hybrid trend filter (EMA + ADX)
    # ATR-based TP/SL calculation
```

### Timing Configuration
```python
SIGNAL_CHECK_INTERVAL = 15      # minutes (15m timeframe)
HOURLY_CHECK_INTERVAL = 30      # minutes (1h timeframe)
PRICE_MONITOR_INTERVAL = 1      # minute
GUIDANCE_INTERVAL = 1           # minute (with 10min cooldown)
HARD_TIMEOUT_MINUTES = 180      # 3 hours
TRADING_START_HOUR = 8          # GMT
TRADING_END_HOUR = 22           # GMT
MORNING_BRIEFING = "06:20"      # UTC
DAILY_RECAP = "06:30"           # UTC
```

---

## 9. Subscription & Billing System

### Plans
| Plan | Price | Billing |
|------|-------|---------|
| 7-Day VIP | $34.99 | Weekly recurring |
| Monthly VIP | $49.00 | Monthly recurring |

### Flow
```
1. User visits EntryLab landing page
2. Selects plan, redirected to Stripe Checkout
3. Payment processed, webhook fires
4. telegram_subscriptions record created
5. User receives Telegram invite link
6. User joins VIP channel, verified via bot
7. Recurring billing via Stripe
8. Failed payment → access revoked
```

### Conversion Tracking
- UTM parameters captured at signup
- Free signup timestamp tracked
- Conversion = free user becomes VIP
- Conversion days calculated automatically

---

## 10. Admin Dashboard

### Navigation Structure
```
Coupon Bot:
├── Templates (upload/manage)
├── Analytics (usage stats)
├── Broadcast (message users)
├── Campaigns (promo campaigns)
└── Settings (bot config)

Forex Bot:
├── Subscriptions (VIP members)
├── Conversions (analytics)
├── Signals Monitor (active signals)
└── Settings (strategy config)
```

### UI Features
- **Dark Navy Theme**: #081028 background
- **Dual Sidebar**: Product switcher (60px) + Feature nav (240px)
- **Hash Routing**: #product/view for navigation
- **Real-time Metrics**: Stripe data with caching
- **Responsive**: Mobile-friendly with collapsible sidebars

---

## 11. Architectural Health & Technical Debt

### Current Rating: 4/10

### Critical Issues
1. **Monolithic server.py** (3,663 lines)
   - All routing, auth, webhooks, bot logic in one file
   - Hard to test, maintain, or extend
   
2. **No Automated Tests**
   - Changes can break production silently
   - No regression protection
   
3. **No Database Migrations**
   - Schema changes are ad-hoc ALTER statements
   - No version control for schema
   
4. **Global State Coupling**
   - Modules depend on globals initialized in server.py
   - Hidden dependencies make refactoring risky
   
5. **Print-Based Logging**
   - No structured logging
   - No alerting on errors

### What Works Well
1. **Modular Strategy System** - Clean plug-and-play design
2. **Separated Bot Core** - milestone_tracker, price_monitor are clean
3. **Environment Config** - Dev/prod switching works
4. **replit.md Documentation** - Architecture decisions recorded

### Recommended Improvements
1. Split server.py into modules (auth, stripe, forex, telegram)
2. Add database migration tool (Alembic)
3. Add smoke tests for critical paths
4. Replace globals with dependency injection
5. Implement structured logging

---

## 12. Deployment

### Production (Digital Ocean)
- **Platform**: Digital Ocean App Platform
- **Config**: `.do/app.yaml`
- **Database**: DO Managed PostgreSQL
- **Storage**: DO Spaces

### Development (Replit)
- **URL**: Replit dev URL
- **Database**: Same or separate PostgreSQL
- **Mode Detection**: Automatic via environment variables

### Webhook Configuration
```
Telegram (Coupon): https://dash.promostack.io/api/telegram-webhook
Telegram (Forex): https://dash.promostack.io/api/forex-telegram-webhook
Stripe: https://dash.promostack.io/api/stripe/webhook
```

---

## Document Version
- **Created**: December 12, 2025
- **Last Updated**: December 12, 2025
- **Author**: Generated from codebase analysis
