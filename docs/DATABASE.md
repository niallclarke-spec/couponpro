# PromoStack Database Schema Reference

## Overview
PromoStack uses PostgreSQL for all persistent data. The database is managed by DigitalOcean in production and Neon on Replit for development.

## Connection Configuration
- **Production**: Uses `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- **Development**: Uses `DATABASE_URL` connection string
- **SSL**: Required in production (`DB_SSLMODE=require`)

## Tenant Isolation Pattern
All tenant-scoped tables include a `tenant_id` column. Every query must filter by tenant_id:
```sql
SELECT * FROM forex_signals WHERE tenant_id = 'entrylab' AND status = 'ACTIVE';
```

## Core Tables

### tenants
Core multi-tenancy table.
| Column | Type | Description |
|--------|------|-------------|
| id | varchar | Primary key (e.g., 'entrylab') |
| name | varchar | Display name |
| created_at | timestamp | Creation timestamp |

### tenant_users
Maps Clerk users to tenants with roles.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| clerk_user_id | varchar | Clerk user ID |
| email | varchar | User email |
| role | varchar | 'admin' or 'member' |
| created_at | timestamp | Creation timestamp |

### tenant_bot_connections
Stores Telegram bot tokens and channel IDs per tenant.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| bot_role | varchar | 'signal_bot' or 'message_bot' |
| bot_token | text | Telegram bot token |
| bot_username | varchar | Bot username |
| channel_id | varchar | Telegram channel ID |
| webhook_secret | varchar | Webhook verification secret |
| created_at | timestamp | Creation timestamp |

### clerk_users
Caches Clerk user information.
| Column | Type | Description |
|--------|------|-------------|
| id | varchar | Clerk user ID (primary key) |
| email | varchar | User email |
| created_at | timestamp | First seen |
| updated_at | timestamp | Last updated |

## Forex Signals Tables

### forex_signals
Trading signals with full lifecycle tracking.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| direction | varchar | 'BUY' or 'SELL' |
| timeframe | varchar | '15min' or '1h' |
| entry_price | decimal | Entry price |
| stop_loss | decimal | Stop loss price |
| take_profit_1/2/3 | decimal | Take profit levels |
| status | varchar | 'ACTIVE', 'TP1_HIT', 'TP2_HIT', 'TP3_HIT', 'STOPPED', 'CLOSED' |
| telegram_message_id | integer | Telegram message ID for editing |
| indicators_used | jsonb | Indicator values at signal generation |
| created_at | timestamp | Signal creation time |
| closed_at | timestamp | When signal closed |

### forex_config
Tenant-specific forex bot configuration.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| setting_key | varchar | Configuration key |
| setting_value | text | Configuration value |
| Unique constraint | | (tenant_id, setting_key) |

Common settings:
- `rsi_oversold`, `rsi_overbought` - RSI thresholds
- `adx_min_strength` - ADX minimum
- `sl_multiplier`, `tp_multiplier` - Risk/reward ratios
- `trading_hours_start`, `trading_hours_end` - Session hours
- `active_strategy` - Current strategy name

## Telegram Subscriptions

### telegram_subscriptions
VIP subscriber management for forex signals.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| email | varchar | Subscriber email |
| stripe_customer_id | varchar | Stripe customer ID |
| stripe_subscription_id | varchar | Stripe subscription ID |
| plan_type | varchar | 'monthly', 'annual', 'lifetime' |
| telegram_user_id | bigint | Telegram user ID |
| telegram_username | varchar | Telegram username |
| status | varchar | 'active', 'cancelled', 'expired' |
| is_converted | boolean | Converted from free trial |
| Unique constraint | | (tenant_id, email) |

### bot_users
Telegram users who have interacted with bots.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| chat_id | bigint | Telegram chat ID |
| username | varchar | Telegram username |
| first_name | varchar | User's first name |
| last_name | varchar | User's last name |
| last_coupon_code | varchar | Last generated coupon |
| Unique constraint | | (tenant_id, chat_id) |

### bot_usage
Tracks bot usage statistics.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| chat_id | bigint | Telegram chat ID |
| template_slug | varchar | Template used |
| coupon_code | varchar | Generated coupon code |
| success | boolean | Generation success |
| error_type | varchar | Error category if failed |
| device_type | varchar | 'desktop' or 'mobile' |
| created_at | timestamp | Usage timestamp |

## Journeys System

### journeys
Defines conversational flows.
| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| tenant_id | varchar | FK to tenants |
| name | varchar | Journey name |
| description | text | Journey description |
| is_active | boolean | Whether journey is active |
| created_at | timestamp | Creation timestamp |

### journey_triggers
Event triggers that start journeys.
| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| journey_id | uuid | FK to journeys |
| trigger_type | varchar | 'deep_link', 'keyword', etc. |
| trigger_config | jsonb | Trigger configuration |
| is_active | boolean | Whether trigger is active |

### journey_steps
Ordered steps within a journey.
| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| journey_id | uuid | FK to journeys |
| step_order | integer | Step sequence number |
| step_type | varchar | 'message', 'question', 'delay', 'wait_for_reply' |
| config | jsonb | Step configuration |

### journey_user_sessions
Tracks user progress through journeys.
| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| tenant_id | varchar | FK to tenants |
| journey_id | uuid | FK to journeys |
| telegram_chat_id | bigint | Telegram chat ID |
| telegram_user_id | bigint | Telegram user ID |
| current_step_id | uuid | Current step FK |
| status | varchar | 'active', 'waiting_delay', 'awaiting_reply', 'completed' |
| answers | jsonb | Collected answers |
| started_at | timestamp | Journey start time |
| completed_at | timestamp | Journey completion time |

### journey_scheduled_messages
Delayed messages queue.
| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| tenant_id | varchar | FK to tenants |
| session_id | uuid | FK to journey_user_sessions |
| step_id | uuid | FK to journey_steps |
| telegram_chat_id | bigint | Telegram chat ID |
| message_content | jsonb | Message to send |
| scheduled_for | timestamp | When to send |
| sent_at | timestamp | When actually sent |
| status | varchar | 'pending', 'sent', 'failed' |

## Cross Promo System

### tenant_crosspromo_settings
Cross-promotion configuration per tenant.
| Column | Type | Description |
|--------|------|-------------|
| tenant_id | varchar | Primary key |
| enabled | boolean | Feature enabled |
| bot_role | varchar | Which bot to use |
| vip_channel_id | varchar | VIP channel ID |
| free_channel_id | varchar | FREE channel ID |
| cta_url | varchar | Call-to-action URL |
| morning_post_time_utc | time | When to post morning news |
| timezone | varchar | Timezone for scheduling |

### crosspromo_jobs
Job queue for cross-promo tasks.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| job_type | varchar | 'morning_news', 'vip_teaser', 'winning_signal' |
| payload | jsonb | Job data |
| status | varchar | 'pending', 'claimed', 'completed', 'failed' |
| claimed_at | timestamp | When job was claimed |
| completed_at | timestamp | When job completed |

## Stripe Integration

### tenant_stripe_settings
Stripe configuration per tenant.
| Column | Type | Description |
|--------|------|-------------|
| tenant_id | varchar | Primary key |
| stripe_account_id | varchar | Connected account ID |
| vip_product_id | varchar | VIP product ID |
| vip_price_id | varchar | VIP price ID |

### tenant_stripe_products / tenant_stripe_prices
Cached Stripe product/price data for API efficiency.

### processed_webhook_events
Idempotency tracking for webhook processing.
| Column | Type | Description |
|--------|------|-------------|
| event_id | varchar | Stripe event ID (primary key) |
| event_type | varchar | Event type |
| processed_at | timestamp | When processed |

## Marketing & Campaigns

### campaigns
Marketing campaign definitions.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| title | varchar | Campaign title |
| description | text | Campaign description |
| start_date | date | Campaign start |
| end_date | date | Campaign end |
| prize | varchar | Prize description |
| status | varchar | 'draft', 'active', 'ended' |

### broadcast_jobs
Queue for broadcast messages to bot users.
| Column | Type | Description |
|--------|------|-------------|
| id | serial | Primary key |
| tenant_id | varchar | FK to tenants |
| message | text | Message to broadcast |
| status | varchar | 'pending', 'processing', 'completed' |
| created_at | timestamp | Job creation time |

## Important Constraints

All tenant-scoped tables have unique constraints to prevent duplicate data:
- `bot_users`: (tenant_id, chat_id)
- `forex_config`: (tenant_id, setting_key)
- `bot_config`: (tenant_id, setting_key)
- `telegram_subscriptions`: (tenant_id, email)
