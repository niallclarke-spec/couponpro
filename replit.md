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
- **Object Storage**: Replit Object Storage integration for persistent template image storage across deployments and restarts. Images are stored with Google Cloud Storage SDK using Replit sidecar authentication.
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
- **Object Storage Integration**: All template images uploaded to Replit Object Storage (bucket: `couponpro-templates`) to persist across Digital Ocean restarts/redeploys. Edit operations preserve existing `imageUrl` values when images aren't re-uploaded.
- **Hybrid Storage Model**: Local `meta.json` files for fast access, with copies in object storage for persistence. Images served from object storage URLs.
- **Modular File Structure**: Organizes templates, assets, and server-side logic logically for maintainability.
- **Environment Variable Configuration**: Uses `.env` file (loaded via python-dotenv) for `OBJECT_STORAGE_BUCKET`, plus `PORT` and `ADMIN_PASSWORD` for flexible deployment and secure credential management.

## External Dependencies
- **Replit Object Storage**: Persistent storage for template images and metadata across deployments (bucket: `couponpro-templates`).
- **Digital Ocean**: Primary production deployment platform, utilizing its Web Service capabilities.
- **Python 3.11**: Runtime environment for the backend server.
- **requirements.txt**: Python dependencies include `google-cloud-storage`, `google-auth`, `python-dotenv`, and `requests`.
- **.env**: Environment configuration file with `OBJECT_STORAGE_BUCKET` variable (loaded via python-dotenv).
- **.do/app.yaml**: Digital Ocean specific application configuration for deployment.

## Recent Changes (Oct 3, 2025)
- **Object Storage Integration**: Implemented Replit Object Storage for template persistence
  - Added `object_storage.py` module with Google Cloud Storage SDK integration
  - Updated upload handler to store images in object storage with `imageUrl` tracking
  - Modified `regenerate_index.py` to prioritize `imageUrl` over legacy local image paths
  - Enhanced delete functionality to remove images and metadata from object storage
  - Fixed critical bug where editing templates without re-uploading images would overwrite object storage URLs with local paths
- **Environment Configuration**: Added python-dotenv to load `.env` file for `OBJECT_STORAGE_BUCKET` configuration
- **Deployment Strategy**: 
  - **Replit**: Primary admin environment with object storage for uploading templates
  - **Digital Ocean**: Public-facing app that serves templates from Replit object storage URLs
  - Object storage gracefully disabled on Digital Ocean (sidecar not available)
- **Backward Compatibility**: System supports both object storage URLs (new templates) and local paths (legacy templates)