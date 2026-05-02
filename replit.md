# PromoStack Promo Gen

## Overview
PromoStack is a platform designed for the rapid generation of branded promotional images, particularly coupons, for social media and messaging. It offers a web application (dash.promostack.io) and a Telegram bot (@promostack_bot) to streamline the creation of marketing assets. The platform also includes a Forex Signals Bot, demonstrating a multi-bot architecture, with strategic plans to evolve into a multi-tenant SaaS Bot Hub marketplace.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform features a dark navy theme with a unified admin dashboard, employing a dual-sidebar layout. It supports hash-based routing, is mobile-responsive, and emphasizes intuitive workflows, real-time visual feedback, live previews, drag-to-draw text manipulation, high-DPI rendering, and color pickers. A consistent design system is enforced using CSS variables.

### Technical Implementations
The frontend uses pure HTML, CSS, and vanilla JavaScript. The backend and API are built with a Python HTTP server. Client-side image generation is handled via canvas manipulation, while the Telegram bot uses server-side Python/Pillow for image rendering. Persistent storage for template images and `meta.json` backups is managed by Digital Ocean Spaces (S3-compatible) with CDN, utilizing `boto3`.

### Dual-Subdomain Architecture
The system employs `admin.promostack.io` for administrative access and `dash.promostack.io` for client dashboards, with host-aware routing controlling access.

### Tenant Onboarding System
A 4-step setup wizard guides new users, automatically provisioning new tenants and tracking onboarding progress.

### Authentication Architecture
Dual authentication is supported: primary Clerk JWT authentication and legacy HMAC-signed `admin_session` cookie authentication. Access levels are defined by host-aware rules, with admin access requiring a whitelisted email. JWKS configuration for Clerk is dynamic, deriving the JWKS URL from the token's `iss` claim.

### Feature Specifications
- **Web Application**: Dynamic template loading, auto-fitting text, live previews, logo overlays, image download/share, and a password-protected admin panel.
- **Telegram Bot Integration**: Server-side rendering for promo images, posting to Telegram channels, and coupon validation.
- **Campaigns & Promotions**: Admin-managed system for creating campaigns with visual overlays and user uploads.
- **FunderPro CRM Integration**: Real-time coupon validation.
- **Telegram Broadcast System**: Admin feature for broadcasting messages.
- **Template Visibility Control**: Admin panel to manage template visibility for the Telegram bot.
- **Bot Analytics Dashboard**: Admin dashboard for tracking generations, users, and performance.
- **Forex Signals Bot**: Automated XAU/USD trading signals with multi-indicator strategies, dynamic TP/SL, AI-powered messages, and performance recaps. It includes a modular strategy system and a centralized pip calculator.
- **Milestone Tracker System**: Unified system for sending signal progress notifications with AI-generated messages and P&L tracking.
- **Journeys System**: Event-triggered, multi-step conversational flows for Telegram bots via deep links or direct messages. It supports various step types, a background scheduler, step analytics, and Telethon user clients for private messages. Includes features for configurable start delays, inline execution for short delays, and production reliability features like per-user async locking, message deduplication, session auto-healing, inactivity auto-completion, stale job guards, journey priority, and await-reply keyword branching. The admin interface is a two-layer design with a searchable list view and a full-page inline editor for managing journeys.
- **Conversion Tracking System**: Full customer lifecycle tracking using unique Telegram invite links, bridging email to Telegram identity, and tracking conversions from free to VIP. Includes UTM attribution and an admin dashboard for funnel and conversion metrics.
- **Connections System**: Tenant-specific bot configuration for Signal Bot and User Account (Telethon), serving as the single source of truth for bot credentials and webhook URLs. Webhooks are re-registered on server startup.
- **BotCredentialResolver**: Centralized service for accessing bot credentials, providing actionable errors.
- **Telegram Send Infrastructure**: Production-grade message sending with caching, short-lived bot instances, explicit cache invalidation, and fail-fast behavior.
- **Telethon User Client**: Telegram User API integration for Journey messaging without bot labels, featuring a singleton client per tenant, rate limiting, and session persistence.
- **Cross Promo Automation**: Automated system for cross-promoting VIP signals in FREE channels, including scheduled jobs, Alpha Vantage gold news integration, atomic job claiming, and an automated morning sequence and end-of-day pip brag. TP-triggered cross-promotions are also handled.
- **Hype Chat Bot**: AI-powered motivational messaging for FREE channels using OpenAI (gpt-4o-mini) with a fixed system prompt and auto-injected pip performance context. Admin UI supports prompt and flow CRUD, a step builder, preview, and analytics. Features a flexible step sequencer for flow orchestration, signal context injection, per-flow daily deduplication, and flow chaining.
- **Navigation Restructure**: Journeys sidebar item is now a parent group with "Support Chat" and "Hype Bot" as children.

### Server Architecture
The server uses a dispatcher pattern with thin request handlers, centralized routing, and middleware. A PostgreSQL advisory lock gates all background workers, ensuring only one instance runs scheduled jobs in multi-instance deployments, with standby instances handling webhooks/API requests.

### Repository Pattern
Domain-specific repository modules centralize database access with consistent error handling, implementing a `Database Availability Pattern` and a `Tenant Isolation Pattern`.

### System Design Choices
Stateless HMAC-signed cookie authentication is used. Digital Ocean Spaces provides persistent storage. The system is modular, uses a hybrid storage model, and is configured via environment variables. Image generation for Telegram uses Pillow, and coupon validation is enforced at the API level. Production robustness for the Telegram bot includes `asyncio.to_thread()`, `AIORateLimiter`, and a single-process webhook architecture. Stripe API is the source of truth for revenue metrics.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage.
- **Digital Ocean PostgreSQL**: Managed database.
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime.
- **Python Packages**: `boto3`, `psycopg2-binary`, `Pillow`, `python-dotenv`, `python-telegram-bot[rate-limiter]`, `aiolimiter`, `telethon`, `cryptg`.
- **OpenAI**: Used by the Hype Chat Bot (gpt-4o-mini).
- **Stripe API**: For revenue metrics.
- **Alpha Vantage**: For gold news integration in cross-promo automation.