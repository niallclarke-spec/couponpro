# CouponPro Promo Gen

## Overview
A static web application that generates promotional images for coupon codes. Users can input their coupon code, select from various templates, and download square or story-sized PNG images with their code automatically placed on the template.

## Recent Changes
- **2025-10-02**: Admin Control Layout Optimization
  - Reorganized control inputs into compact 2-row layout for space efficiency
  - Row 1: Left, Top, Height (placement coordinates)
  - Row 2: Width, Font Size, Logo checkbox (all inline)
  - HTML5 number inputs include built-in spinner controls for easy up/down adjustment
  - Users can click arrows or type values manually for precise control

- **2025-10-02**: Admin Login Page Styling
  - Updated login heading to white text (previously blue)
  - Reduced heading font size by 20% (from 28px to 22px)
  - Improved visual hierarchy with centered logo positioning

- **2025-10-02**: Admin Live Preview Feature
  - Added real-time preview canvases showing square and story formats
  - Each preview positioned directly within its controls section for easy adjustment
  - Blue semi-transparent bounding box shows exact coupon placement area
  - Preview displays "PREVIEW" text with current placement settings
  - Live updates when adjusting coordinates, alignment, or font size
  - Automatically loads uploaded template images into preview
  - Users can now visually verify coupon placement before uploading
  - Redesigned admin layout: two-column grid with controls on left, large preview on right

- **2025-10-02**: Admin Interface UI/UX Improvements
  - Updated admin page with dark theme matching front page (black background, dark containers)
  - Added FunderPro logo to admin page header
  - Moved admin interface to cleaner /admin route (with 301 redirect from /admin/)
  - Fixed asset paths to use absolute URLs for proper routing
  - Removed legacy Decap CMS admin directory
  - Admin accessible at `/admin` with improved visual consistency

- **2025-10-02**: Digital Ocean Deployment Configuration  
  - Added requirements.txt and runtime.txt for Python buildpack detection
  - Created .do/app.yaml for Web Service configuration
  - Updated server.py to use PORT environment variable (8080 for DO, 5000 for Replit)
  - Successfully deployed as Python Web Service on Digital Ocean

- **2025-10-02**: Custom Admin Interface with Password Authentication
  - Created admin-simple.html: Simple, user-friendly template upload interface
  - Added password authentication using ADMIN_PASSWORD secret
  - Implemented secure session-based login with HttpOnly cookies
  - Added POST /api/login, /api/logout, and /api/upload-template endpoints
  - Automatic slug validation and path traversal protection
  - Auto-generates meta.json and regenerates index.json after upload

- **2025-10-02**: GitHub import to Replit
  - Installed Python 3.11
  - Created server.py to serve static files on port 5000 with cache-control headers
  - Configured workflow "Server" to auto-start the Python HTTP server
  - Set up autoscale deployment configuration
  - Verified frontend works correctly with live preview and template loading

## Project Architecture

### Technology Stack
- **Frontend**: Pure HTML, CSS, and vanilla JavaScript
- **Admin Interface**: Custom password-protected upload form (admin-simple.html)
- **Server**: Python HTTP server with authentication and file upload endpoints

### Project Structure
```
/
├── index.html              # Main application page
├── admin-simple.html       # Admin interface (served at /admin)
├── server.py               # Python HTTP server with routing
├── regenerate_index.py     # Template index regeneration script
├── requirements.txt        # Python dependencies
├── runtime.txt            # Python runtime version
├── .do/
│   └── app.yaml           # Digital Ocean deployment config
├── assets/
│   ├── templates/          # Template images and metadata
│   │   ├── index.json      # Template manifest
│   │   └── [template-name]/
│   │       ├── meta.json   # Template configuration
│   │       ├── square.png  # Square format image
│   │       └── story.png   # Story format image
│   ├── fp-affiliate-logo.svg
│   └── fp-site-logo.png
└── templates.json          # Main template configuration
```

### Key Features
1. **Dynamic Template Loading**: Automatically discovers templates from GitHub or local storage
2. **Auto-fit Text**: Automatically sizes coupon code text to fit within defined template boxes
3. **Live Preview**: Real-time canvas rendering of both square and story formats
4. **Logo Overlay**: Optional FunderPro logo in top-left corner
5. **Share/Download**: Download or share generated images directly from the browser
6. **Template Management**: Decap CMS interface for adding/editing templates

### How It Works
1. User enters a coupon code (automatically sanitized and uppercased)
2. Selects a template from the dropdown
3. App loads the template images and renders the coupon code with auto-fitted text
4. User can download square (1:1) or story (9:16) formatted images
5. Optional logo overlay can be toggled on/off

## Development
- **Run**: The server starts automatically via the workflow
- **Port**: 5000
- **Access Admin**: Navigate to `/admin` to manage templates

## Deployment
- **Production**: Currently deployed on Digital Ocean at https://couponpro-o4fjo.ondigitalocean.app
- **Replit Deployment**: Also configured for autoscale deployment with static file serving (optional)
