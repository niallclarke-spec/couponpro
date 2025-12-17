# PromoStack Environment Variables Reference

## Overview
This document lists all environment variables used by PromoStack. Variables are accessed through `core/config.py` to centralize configuration.

## Required Variables

### Database
| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes (Replit) | Full PostgreSQL connection string |
| `DB_HOST` | Yes (DO) | Database host |
| `DB_PORT` | Yes (DO) | Database port (usually 25060) |
| `DB_NAME` | Yes (DO) | Database name |
| `DB_USER` | Yes (DO) | Database username |
| `DB_PASSWORD` | Yes (DO) | Database password |
| `DB_SSLMODE` | No | SSL mode (default: 'require') |

### Server
| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No | Server port (default: 5000 Replit, 8080 DO) |
| `DOMAIN` | No | Public domain for webhook URLs |
| `ADMIN_PASSWORD` | Yes | HMAC signing key for legacy auth |

### Telegram Bots
| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Coupon bot token |
| `FOREX_BOT_TOKEN` | Prod | Forex signal bot token (production) |
| `ENTRYLAB_TEST_BOT` | Dev | Forex signal bot token (development) |
| `FOREX_CHANNEL_ID` | No | Default forex channel ID |

### Stripe
| Variable | Required | Description |
|----------|----------|-------------|
| `STRIPE_SECRET_KEY` | Yes | Stripe API secret key |
| `STRIPE_SECRET` | Alt | Alternative name for Stripe key |
| `TEST_STRIPE_SECRET` | Dev | Test mode Stripe key |
| `STRIPE_WEBHOOK_SECRET` | Prod | Webhook signature verification |
| `TEST_STRIPE_WEBHOOK_SECRET` | Dev | Test webhook secret |
| `STRIPE_PUBLISHABLE_KEY` | No | Public key for frontend |

### DigitalOcean Spaces (Object Storage)
| Variable | Required | Description |
|----------|----------|-------------|
| `SPACES_ACCESS_KEY` | Yes | S3 access key |
| `SPACES_SECRET_KEY` | Yes | S3 secret key |
| `SPACES_BUCKET` | No | Bucket name (default: 'couponpro-templates') |
| `SPACES_REGION` | No | Region (default: 'lon1') |

### External APIs
| Variable | Required | Description |
|----------|----------|-------------|
| `TWELVE_DATA_API_KEY` | Yes | Market data API key |
| `FUNDERPRO_PRODUCT_ID` | Yes | FunderPro coupon validation |
| `ENTRYLAB_API_KEY` | No | EntryLab API integration |

### Authentication (Clerk)
| Variable | Required | Description |
|----------|----------|-------------|
| `CLERK_ALLOWED_ISSUERS` | Prod | Comma-separated allowlist of Clerk issuers |

Note: JWKS URL is derived dynamically from each token's `iss` claim. No environment variable needed.

### AI Integration
| Variable | Required | Description |
|----------|----------|-------------|
| `AI_INTEGRATIONS_OPENAI_API_KEY` | Auto | Replit's OpenAI integration (auto-populated) |
| `AI_INTEGRATIONS_OPENAI_BASE_URL` | Auto | Replit's OpenAI base URL (auto-populated) |

### Scheduler
| Variable | Required | Description |
|----------|----------|-------------|
| `TENANT_ID` | Prod | Tenant ID for forex scheduler (e.g., 'entrylab') |
| `LOG_LEVEL` | No | Logging verbosity (default: 'INFO') |

### Deployment Flags
| Variable | Required | Description |
|----------|----------|-------------|
| `REPLIT_DEPLOYMENT` | No | Set to '1' for Replit production |

## DigitalOcean App Platform Configuration

The `.do/app.yaml` file defines all variables for production deployment. Secrets are marked with `type: SECRET` and `scope: RUN_TIME`.

Example from app.yaml:
```yaml
envs:
  - key: PORT
    value: "8080"
  - key: TENANT_ID
    value: "entrylab"
  - key: ADMIN_PASSWORD
    scope: RUN_TIME
    type: SECRET
  - key: STRIPE_SECRET_KEY
    scope: RUN_TIME
    type: SECRET
```

## Development vs Production

### Development (Replit)
- Uses `DATABASE_URL` for database connection
- Uses `ENTRYLAB_TEST_BOT` for forex bot
- Uses `TEST_STRIPE_SECRET` for Stripe
- OpenAI keys auto-populated by Replit integration

### Production (DigitalOcean)
- Uses `DB_*` variables for database connection
- Uses `FOREX_BOT_TOKEN` for forex bot
- Uses `STRIPE_SECRET_KEY` for Stripe
- Must set `TENANT_ID` for forex scheduler
- Should set `CLERK_ALLOWED_ISSUERS` for security

## Adding New Environment Variables

1. Add getter method to `core/config.py`
2. Document in this file
3. Add to `.do/app.yaml` if needed for production
4. Update `replit.md` with the new variable
