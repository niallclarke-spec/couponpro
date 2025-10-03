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
- **File Persistence**: Explicit `fsync()` calls ensure immediate disk persistence of uploaded template files and metadata, mitigating data loss on ephemeral filesystems.
- **Template Management**: Templates are stored in a structured directory, with `meta.json` holding configuration for each template. An `index.json` acts as a manifest.

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
- **Ephemeral Filesystem Handling**: Implemented explicit file persistence and stateless sessions to ensure reliability on platforms like Digital Ocean.
- **Modular File Structure**: Organizes templates, assets, and server-side logic logically for maintainability.
- **Environment Variable Configuration**: Utilizes `PORT` and `ADMIN_PASSWORD` environment variables for flexible deployment and secure credential management.

## External Dependencies
- **Digital Ocean**: Primary production deployment platform, utilizing its Web Service capabilities.
- **Python 3.11**: Runtime environment for the backend server.
- **requirements.txt**: Specifies Python dependencies for the server.
- **.do/app.yaml**: Digital Ocean specific application configuration for deployment.