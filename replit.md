# PromoStack Promo Gen

## Overview
PromoStack is a promotional image generation platform offering web and Telegram bot interfaces. It enables users to rapidly create branded coupon images for marketing on social media and messaging platforms. The platform's core purpose is to streamline the creation of visually appealing marketing assets, accessible via a web application (dash.promostack.io) or through commands to @promostack_bot in Telegram channels.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The platform features a consistent dark theme across both user-facing and administration interfaces. The admin panel is designed for intuitive workflow, incorporating centered control elements, real-time visual feedback through live previews, and a drag-to-draw interface for defining coupon text areas. Key design elements include high-DPI rendering for crisp output and color pickers for text customization.

### Technical Implementations
The frontend uses pure HTML, CSS, and vanilla JavaScript for a lightweight experience. The backend, including the admin panel and API, is a Python HTTP server (`server.py`). Image generation occurs client-side via canvas manipulation for the web app, including auto-fitting text and optional logo overlays, while the Telegram bot uses server-side Python/Pillow for rendering. Authentication uses HMAC-signed cookie authentication for stateless session management. Template images and `meta.json` backups are stored persistently in Digital Ocean Spaces (S3-compatible object storage) with CDN-enabled public URLs, accessed via `boto3`.

### Feature Specifications
- **Web Application (V1)**: Dynamic template loading, auto-fit text, live previews (square/portrait), optional logo overlay, image download/share, and a password-protected admin panel for template management (upload, edit, bulk delete).
- **Telegram Bot Integration (V2)**: The @promostack_bot processes commands like `/template-name/COUPONCODE`, generating and posting promo images directly to Telegram channels using server-side Python/Pillow rendering. It supports flexible template matching and webhook integration.
- **Campaigns & Promotions (V3)**: An admin-managed system for creating promotional campaigns with titles, descriptions, dates, and target platforms. Campaigns automatically transition statuses. Users can participate by submitting emails and social media URLs, which admins can track. This feature uses a PostgreSQL database for campaign and submission data with dedicated API endpoints and admin/frontend interfaces.

### System Design Choices
The system uses stateless HMAC-signed cookie authentication to support ephemeral environments. All template images are stored in Digital Ocean Spaces for persistence across deployments, serving as the universal source of truth. A hybrid storage model utilizes local `meta.json` files for quick access while backing them up to object storage. The architecture is modular, using environment variables for configuration (`SPACES_ACCESS_KEY`, `TELEGRAM_BOT_TOKEN`, `DB_HOST`, etc.). Telegram image generation uses Pillow for accurate, stroke-artifact-free rendering, matching web app quality.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible object storage for persistent template images (bucket: `couponpro-templates`, region: LON1) with CDN.
- **Digital Ocean PostgreSQL**: Managed database for campaigns and submissions (database: `promostack-db`, region: LON1).
- **Digital Ocean**: Primary production deployment platform.
- **Python 3.11**: Backend runtime environment.
- **`requirements.txt`**: Key Python packages include `boto3` (for S3 interaction), `psycopg2-binary` (PostgreSQL driver), `Pillow` (image processing), `python-dotenv`, and `requests` (for Telegram API).
- **Environment Secrets**: `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`, `TELEGRAM_BOT_TOKEN`, `ADMIN_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- **.do/app.yaml**: Digital Ocean specific application configuration.