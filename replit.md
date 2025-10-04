# PromoStack Promo Gen

## Overview
PromoStack is a promotional image generation platform with two interfaces: a web application and a Telegram bot. Users can generate branded coupon images either through the web interface (dash.promostack.io) or by sending commands to @promostack_bot in Telegram channels. The platform enables quick creation of visually appealing marketing assets for social media and messaging platforms.

## User Preferences
I prefer clear, concise communication. When suggesting changes or explaining concepts, please provide a high-level summary first, followed by details if necessary. I value iterative development and would like to be consulted before any major architectural changes or significant code refactoring. Please prioritize solutions that are robust and scalable, especially concerning file persistence and session management in ephemeral environments. Ensure that the visual design remains consistent and user-friendly, particularly in the admin interface.

## System Architecture

### UI/UX Decisions
The application features a dark theme for both the frontend and admin interfaces, consistent with brand aesthetics. The admin panel prioritizes intuitive workflow with centered control elements, visual feedback through real-time previews, and a drag-to-draw interface for defining coupon text areas. Key design elements include:
- **Consistent Dark Theme**: Applies to both user-facing and administration sections.
- **Real-time Previews**: Live canvas rendering for square and story formats in the admin, showing coupon placement.
- **Drag-to-Draw Interface**: Replaces manual slider adjustments for defining coupon text boxes with visual dragging and nudging for fine-tuning.
- **Color Pickers**: Allows selection of font color (Red/White) for coupon text.
- **High-DPI Rendering**: Utilizes `devicePixelRatio` and image smoothing for crisp image output.

### Technical Implementations
- **Frontend**: Built with pure HTML, CSS, and vanilla JavaScript for a lightweight and performant user experience.
- **Backend (Admin & API)**: A Python HTTP server (`server.py`) handles template uploads, authentication, and file serving.
- **Image Generation**: Client-side canvas manipulation for rendering coupon codes onto templates, including auto-fitting text and optional logo overlays.
- **Authentication**: HMAC-signed cookie authentication for stateless, secure session management, compatible with ephemeral environments.
- **Object Storage**: Digital Ocean Spaces (S3-compatible) integration for persistent template image storage across deployments and restarts. Images are stored using boto3 S3 client with CDN-enabled public URLs.
- **File Persistence**: Template images stored in object storage with URLs tracked in `imageUrl` fields. Local `meta.json` files backed up to object storage for redundancy.
- **Template Management**: Templates use `imageUrl` fields in `meta.json` for object storage URLs. The `regenerate_index.py` script prioritizes `imageUrl` over legacy local paths for backward compatibility.

### Feature Specifications

**V1 - Web Application:**
- **Dynamic Template Loading**: Templates are automatically discovered and loaded from the `assets/templates/` directory.
- **Auto-fit Text**: Coupon code text automatically resizes to fit within defined bounding boxes on templates.
- **Live Preview**: Real-time canvas rendering of both square and portrait formats during template creation/editing.
- **Logo Overlay**: Optional PromoStack logo can be applied to generated images.
- **Share/Download**: Users can download generated images or share them directly.
- **Admin Interface**: A custom, password-protected admin panel (`admin-simple.html`) for uploading, editing, and bulk deleting templates.
- **Editable Templates**: Existing templates can be loaded into the admin for placement adjustments without re-uploading base images.

**V2 - Telegram Bot Integration:**
- **Bot Handle**: @promostack_bot (Telegram bot for channel posting)
- **Command Format**: `/template-name/COUPONCODE` (e.g., `/flash-sale/SAVE50`)
- **Flexible Matching**: Normalizes template slugs to handle variations (flashsale → flash-sale)
- **Server-side Generation**: Python/Pillow-based image generation (`telegram_image_gen.py`) for webhook responses
- **Channel Support**: Works in Telegram channels when bot is added as admin with "Post Messages" permission
- **Automatic Posting**: Bot automatically generates and posts promo images directly to the channel
- **Webhook Integration**: Production webhook at `https://dash.promostack.io/api/telegram-webhook`

### System Design Choices
- **Stateless Sessions**: Transitioned from file-based sessions to HMAC-signed cookie authentication to support ephemeral environments and multi-instance deployments.
- **Object Storage Integration**: All template images uploaded to Digital Ocean Spaces (bucket: `couponpro-templates`, region: LON1) to persist across deployments. Works universally on both Replit and Digital Ocean. Edit operations preserve existing `imageUrl` values when images aren't re-uploaded.
- **Hybrid Storage Model**: Local `meta.json` files for fast access, with copies in object storage for persistence. Images served from object storage URLs.
- **Modular File Structure**: Organizes templates, assets, and server-side logic logically for maintainability.
- **Environment Variable Configuration**: Uses environment secrets for `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`, `TELEGRAM_BOT_TOKEN`, plus `PORT` and `ADMIN_PASSWORD` for flexible deployment and secure credential management.
- **Telegram Image Generation**: Server-side image rendering using Pillow with bbox-based text positioning for accurate vertical centering, matching web app visual output without stroke artifacts.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible persistent storage for template images with CDN (bucket: `couponpro-templates`, region: LON1). Works on both Replit and Digital Ocean deployments.
- **Digital Ocean**: Primary production deployment platform, utilizing its Web Service capabilities.
- **Python 3.11**: Runtime environment for the backend server.
- **requirements.txt**: Python dependencies include `boto3` (S3-compatible storage client), `python-dotenv`, `Pillow` (image generation), and `requests` (Telegram API).
- **Environment Secrets**: Secure credentials stored as secrets - `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`, `TELEGRAM_BOT_TOKEN`, `ADMIN_PASSWORD`.
- **.do/app.yaml**: Digital Ocean specific application configuration for deployment.

## Custom Domains (promostack.io)
- **admin.promostack.io**: Admin panel for uploading and managing templates (CNAME → Digital Ocean App)
- **dash.promostack.io**: Public frontend for generating coupon images + Telegram webhook endpoint (CNAME → Digital Ocean App)
- **promostack.io**: Reserved for future landing page
- **Domain Registrar**: Hostinger (DNS managed via Hostinger hPanel)
- **Routing**: Server checks Host header and routes requests to appropriate pages. Accessing `/admin` from non-admin domains redirects to admin.promostack.io for security

## Telegram Bot (@promostack_bot)
- **Bot Username**: @promostack_bot
- **Usage**: Add bot as admin to Telegram channel with "Post Messages" permission
- **Command Format**: `/template-slug/COUPONCODE` (e.g., `/flash-sale/WELCOME30`)
- **Webhook URL**: `https://dash.promostack.io/api/telegram-webhook` (production)
- **Bot Features**: 
  - Automatic template matching with slug normalization
  - Server-side image generation matching web app quality
  - Instant posting of promo images to channels
  - Support for all uploaded templates

## Version History

### V2.5 - Telegram Integration Stable Release (Oct 4, 2025) ✅ MILESTONE
**This version includes full Telegram bot integration with stable template management**

**Key Features:**
- ✅ Telegram bot (@promostack_bot) fully operational for channel posting
- ✅ Fixed critical metadata corruption bugs in template upload/delete system
- ✅ Spaces-based index regeneration (source of truth)
- ✅ Reliable template deletion and management
- ✅ Web app and Telegram bot both production-ready

**Critical Fixes:**
- Fixed metadata corruption caused by in-place dictionary mutation
- Rewrote `regenerate_index.py` to use Digital Ocean Spaces as source of truth
- Eliminated "ghost template" resurrection after deletion
- Fixed Spaces image permissions (403 errors resolved)

## Recent Changes (Oct 3-4, 2025)
- **V2 Telegram Bot Integration** (Oct 4, 2025):
  - Created @promostack_bot for automated promo image generation in Telegram channels
  - Built server-side image generation engine (`telegram_image_gen.py`) porting canvas logic to Python/Pillow
  - Implemented command parser (`telegram_bot.py`) with flexible template slug matching
  - Added `/api/telegram-webhook` endpoint to `server.py` for webhook handling
  - Fixed channel post detection (channels use `channel_post` instead of `message` in Telegram API)
  - Corrected text positioning using bbox-based vertical centering for accurate placement
  - Removed black stroke artifact to match web app clean appearance
  - Deployed to production with webhook at `https://dash.promostack.io/api/telegram-webhook`
  - Added `TELEGRAM_BOT_TOKEN` to Digital Ocean environment secrets
  - Production bot fully operational in Telegram channels
- **Download Button CORS Fix**: Fixed download buttons not working due to cross-origin security error
  - Added `crossOrigin = "anonymous"` to all image loading in `index.html` (logo, templates, variants)
  - Configured Digital Ocean Spaces CORS settings to allow GET/HEAD requests from all origins
  - Canvas can now export "tainted" images loaded from CDN as downloadable PNGs
- **PromoStack Rebranding**: Rebranded from CouponPro to PromoStack
  - New yellow/white PromoStack logo (assets/promostack-logo.png)
  - Updated all branding references across frontend and admin pages
  - Changed "Story" label to "Portrait" throughout UI
  - Removed main heading on dash page for cleaner design
  - Increased logo sizes: frontend 220px, admin panel 220px, login 280px
- **Template Deletion Fix**: Fixed critical bug preventing template deletion in production
  - Delete handler now prioritizes object storage deletion over local file deletion
  - Works correctly on Digital Ocean where templates only exist in Spaces (no local directories)
  - Template deletion now succeeds if either object storage or local deletion succeeds
  - Added better logging for deletion debugging
- **Digital Ocean Spaces Migration**: Migrated from Replit Object Storage to Digital Ocean Spaces for universal compatibility
  - Rewrote `object_storage.py` module to use boto3 S3-compatible client instead of Google Cloud Storage
  - Configured Digital Ocean Spaces: bucket `couponpro-templates`, region LON1, CDN enabled
  - Added secure environment secrets: `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`
  - Object storage now works on both Replit (dev) and Digital Ocean (prod) without platform-specific code
  - Updated `requirements.txt` to use `boto3` instead of Google Cloud dependencies
- **Object Storage Features**: 
  - Upload handler stores images in Spaces with `imageUrl` tracking
  - Modified `regenerate_index.py` to prioritize `imageUrl` over legacy local image paths
  - Enhanced delete functionality to remove images and metadata from Spaces
  - Fixed critical bug where editing templates without re-uploading images would overwrite object storage URLs with local paths
- **Deployment Strategy**: 
  - **Replit**: Development environment with admin access for uploading templates to Spaces
  - **Digital Ocean**: Production public-facing app serving templates from Spaces CDN URLs
  - Single object storage backend (Spaces) works seamlessly on both platforms
- **Backward Compatibility**: System supports both object storage URLs (new templates) and local paths (legacy templates)