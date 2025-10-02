# CouponPro Promo Gen

## Overview
A static web application that generates promotional images for coupon codes. Users can input their coupon code, select from various templates, and download square or story-sized PNG images with their code automatically placed on the template.

## Recent Changes
- **2025-10-02**: GitHub import to Replit
  - Installed Python 3.11
  - Created server.py to serve static files on port 5000 with cache-control headers
  - Configured workflow "Server" to auto-start the Python HTTP server
  - Set up autoscale deployment configuration
  - Verified frontend works correctly with live preview and template loading

## Project Architecture

### Technology Stack
- **Frontend**: Pure HTML, CSS, and vanilla JavaScript
- **CMS**: Decap CMS (formerly Netlify CMS) for template management
- **Server**: Python HTTP server for serving static files

### Project Structure
```
/
├── index.html              # Main application page
├── server.py               # Python HTTP server for static files
├── admin/
│   ├── index.html          # Decap CMS admin interface
│   └── config.yml          # CMS configuration
├── assets/
│   ├── templates/          # Template images and metadata
│   │   ├── index.json      # Template manifest
│   │   └── [template-name]/
│   │       ├── meta.json   # Template configuration
│   │       ├── square.png  # Square format image
│   │       └── story.png   # Story format image
│   ├── uploads/            # CMS uploaded files
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
- **Access Admin**: Navigate to `/admin/` to manage templates

## Deployment
- **Production**: Currently deployed on Digital Ocean at https://couponpro-o4fjo.ondigitalocean.app
- **Replit Deployment**: Also configured for autoscale deployment with static file serving (optional)
