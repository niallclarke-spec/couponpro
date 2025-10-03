# CouponPro Promo Gen

## Overview
A static web application that generates promotional images for coupon codes. Users can input their coupon code, select from various templates, and download square or story-sized PNG images with their code automatically placed on the template.

## Recent Changes
- **2025-10-03**: Image Rendering Race Condition Fix
  - Fixed critical rendering bug where square/story images would randomly fail to load
  - Added await img.decode() to ensure images fully load before rendering
  - Reset canvas transform (setTransform) to prevent coordinate accumulation
  - Made square and story rendering completely independent to prevent overwrites
  - Eliminated random template appearance/disappearance after refresh
  - Fixed incorrect coupon placement caused by transform scaling bugs
  - Both admin and frontend now render both formats consistently and correctly

- **2025-10-03**: Delete Debugging & Logging Enhancement
  - Added comprehensive logging to delete endpoint for troubleshooting
  - Enhanced error messages: "Unauthorized - please login again" for failed auth
  - Logs now track: delete requests, authentication status, template removal, index regeneration
  - Confirmed cache-control headers already properly configured (no-cache, no-store)
  - Index regeneration happens synchronously before delete response

- **2025-10-03**: Critical Position & Performance Fixes
  - Fixed admin interface not loading saved coordinates when editing templates
  - Admin now correctly reads from nested `meta.square.box.*` structure in meta.json
  - Added debouncing (50ms) to preview rendering to eliminate performance lag
  - Separated immediate vs debounced preview updates for responsive UI
  - Templates now display at exact saved positions when loaded in Current Assets

- **2025-10-03**: Font Color Bug Fix
  - Fixed frontend not reading fontColor from meta.json templates
  - Color selection now properly applies to downloaded/shared images
  - Templates saved with red color now display correctly in frontend

- **2025-10-03**: Admin UI Layout Refinement
  - Centered all control elements for better visual hierarchy
  - Font Size slider now centered above other controls with reduced width (200px max)
  - Show Logo checkbox moved to its own row below Font Size
  - Fine-Tune Position label centered above nudge buttons
  - Nudge buttons reduced to 32px (from 36px) for more compact appearance
  - Color selectors moved below nudge controls and centered
  - File upload boxes now have solid red border with enhanced glow effect (no dashes)
  - Preview placeholder text changed from "PREVIEW" to "COUPON-AREA"
  - All controls now vertically stacked and centered for intuitive workflow
  - Fixed vAlign to use 'middle' instead of 'bottom' for better text centering

- **2025-10-03**: Drag-to-Draw Interface & Font Color Picker
  - Replaced manual slider adjustments with intuitive drag-to-draw interface
  - Click and drag directly on preview canvases to define coupon text area
  - Real-time visual feedback with dotted selection rectangle while dragging
  - Automatic coordinate conversion from pixels to percentages
  - Removed all positioning sliders (Left-Right, Top-Bottom, Width) - drag-to-draw is now the exclusive method
  - Added nudge buttons (↑ ↓ ← →) for precise fine-tuning after drawing (0.5% increments)
  - Blue bounding box only shows during active dragging - clean preview after placement
  - Added font color picker with two visual swatches: Red (#FF273E) and White (#FFFFFF)
  - Independent color selection per format
  - Selected color shows visual indicator (border + glow effect)
  - Color stored in meta.json and applied across admin, frontend, downloads, and shares
  - Crosshair cursor and helpful hints guide user interaction
  - Minimum drag threshold prevents accidental tiny boxes
  - Auto-fit logic maximizes text to fill the drawn box area
  - Preview text centered vertically in middle of box (not bottom)
  - Backwards compatible - existing templates without fontColor still work

- **2025-10-03**: Template Edit Without Re-upload
  - Made image uploads optional when editing existing templates
  - Users can now update coupon placement without re-uploading images
  - Added helpful hint text: "Leave empty to keep existing image"
  - Server now only updates images if new files are provided
  - Enables quick adjustments to placement settings on existing templates

- **2025-10-03**: Session Cookie Fix for HTTPS
  - Added Secure flag to session cookies for HTTPS environments (Digital Ocean)
  - Fixed login persistence issues where users were logged out on page refresh
  - Cookies now properly persist across page reloads on both Replit (HTTP) and Digital Ocean (HTTPS)
  - Resolved "Unauthorized" errors during template deletion on production

- **2025-10-03**: Bulk Template Delete Feature
  - Added checkboxes to each template in Current Assets list
  - Added "Select All" checkbox to select/deselect all templates at once
  - Added "Delete Selected" button for bulk deletion
  - Bulk delete shows confirmation with list of templates to be deleted
  - Shows summary of successful/failed deletions after bulk operation
  - Fixed "Unauthorized" error by adding credentials to delete API requests
  - Indeterminate checkbox state when some (not all) templates selected

- **2025-10-02**: High-Quality Canvas Rendering
  - Increased canvas resolution using devicePixelRatio for crisp, sharp images
  - Applied high-DPI rendering to both frontend previews and admin panel
  - Enabled image smoothing with 'high' quality setting
  - Fixed pixelated text and template images
  - Improved download and share image quality
  - Added missing logo rendering to download/share functions

- **2025-10-02**: Template Delete Feature & Login Page Enhancement
  - Added delete button (red trash icon) to each template in Current Assets list
  - Delete removes entire template folder and both images, then regenerates index
  - Confirmation dialog prevents accidental deletion
  - Added "Visit Frontend" button on login page with transparent fill and blue stroke
  - Fixed button widths: login page buttons full width, admin panel buttons normal size
  - Server now uses SO_REUSEADDR to prevent port binding issues on restart

- **2025-10-02**: Enhanced Control System with Sliders
  - Added smooth range sliders for placement controls (Left-Right, Top-Bottom, Width, Font Size)
  - Removed Height control (Font Size automatically handles vertical sizing)
  - Clearer labels: "Left - Right" and "Top - Bottom" for intuitive understanding
  - Width default changed to 25% for better initial positioning
  - Sliders bidirectionally sync with number inputs in real-time
  - Significantly reduces clicking needed to position coupon area
  - Blue slider thumbs with hover animations for better UX
  - Controls maintain dual-input method: sliders for speed, numbers for precision

- **2025-10-02**: Editable Template System & List View
  - Current Assets tab now displays templates in clean list format
  - Click any template to load it into edit mode with live preview
  - Edit mode populates all placement settings and preview windows
  - Allows tweaking coupon placement on existing templates without re-upload
  - Dark background restored for admin and login pages
  
- **2025-10-02**: Admin Interface Simplification & Modern Tabs
  - Removed horizontal/vertical alignment dropdowns (now defaults to center/bottom)
  - Hidden slug field from UI (auto-generated from template name)
  - Added modern tab navigation: "Upload Template" and "Current Assets"
  - Simplified controls now show only essential placement settings

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
