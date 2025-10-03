# CouponPro Promo Gen

## Overview
CouponPro Promo Gen is a static web application designed to generate promotional images for coupon codes. Users can input a coupon code, select from various pre-defined templates, and then download square or story-sized PNG images with their coupon code automatically rendered onto the chosen template. The project aims to provide an intuitive tool for creating visually appealing marketing assets quickly.

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
- **Dynamic Template Loading**: Templates are automatically discovered and loaded from the `assets/templates/` directory.
- **Auto-fit Text**: Coupon code text automatically resizes to fit within defined bounding boxes on templates.
- **Live Preview**: Real-time canvas rendering of both square and story formats during template creation/editing.
- **Logo Overlay**: Optional FunderPro logo can be applied to generated images.
- **Share/Download**: Users can download generated images or share them directly.
- **Admin Interface**: A custom, password-protected admin panel (`admin-simple.html`) for uploading, editing, and bulk deleting templates.
- **Editable Templates**: Existing templates can be loaded into the admin for placement adjustments without re-uploading base images.

### System Design Choices
- **Stateless Sessions**: Transitioned from file-based sessions to HMAC-signed cookie authentication to support ephemeral environments and multi-instance deployments.
- **Object Storage Integration**: All template images uploaded to Digital Ocean Spaces (bucket: `couponpro-templates`, region: LON1) to persist across deployments. Works universally on both Replit and Digital Ocean. Edit operations preserve existing `imageUrl` values when images aren't re-uploaded.
- **Hybrid Storage Model**: Local `meta.json` files for fast access, with copies in object storage for persistence. Images served from object storage URLs.
- **Modular File Structure**: Organizes templates, assets, and server-side logic logically for maintainability.
- **Environment Variable Configuration**: Uses environment secrets for `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`, plus `PORT` and `ADMIN_PASSWORD` for flexible deployment and secure credential management.

## External Dependencies
- **Digital Ocean Spaces**: S3-compatible persistent storage for template images with CDN (bucket: `couponpro-templates`, region: LON1). Works on both Replit and Digital Ocean deployments.
- **Digital Ocean**: Primary production deployment platform, utilizing its Web Service capabilities.
- **Python 3.11**: Runtime environment for the backend server.
- **requirements.txt**: Python dependencies include `boto3` (S3-compatible storage client) and `python-dotenv`.
- **Environment Secrets**: Secure credentials stored as Replit secrets - `SPACES_ACCESS_KEY`, `SPACES_SECRET_KEY`, `SPACES_REGION`, `SPACES_BUCKET`.
- **.do/app.yaml**: Digital Ocean specific application configuration for deployment.

## Custom Domains (promostack.io)
- **admin.promostack.io**: Admin panel for uploading and managing templates (CNAME → Digital Ocean App)
- **dash.promostack.io**: Public frontend for generating coupon images (CNAME → Digital Ocean App)
- **promostack.io**: Reserved for future landing page
- **Domain Registrar**: Hostinger (DNS managed via Hostinger hPanel)
- **Routing**: Server checks Host header and routes requests to appropriate pages. Accessing `/admin` from non-admin domains redirects to admin.promostack.io for security

## Recent Changes (Oct 3, 2025)
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