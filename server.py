#!/usr/bin/env python3
import http.server
import socketserver
import os
import json
import subprocess
import secrets
import base64
from urllib.parse import urlparse, parse_qs
import mimetypes
import cgi
from http import cookies
import time
import hmac
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Try to import object storage (only available on Replit)
try:
    from object_storage import ObjectStorageService
    OBJECT_STORAGE_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Object storage not available (running outside Replit): {e}")
    OBJECT_STORAGE_AVAILABLE = False

# Import Telegram bot handler
try:
    import telegram_bot
    TELEGRAM_BOT_AVAILABLE = True
except Exception as e:
    print(f"[INFO] Telegram bot not available: {e}")
    TELEGRAM_BOT_AVAILABLE = False

# Import database module for campaigns
try:
    import db
    schema_initialized = db.db_pool.initialize_schema()
    DATABASE_AVAILABLE = schema_initialized
    if not DATABASE_AVAILABLE:
        print(f"[INFO] Database not available - campaigns feature disabled")
except Exception as e:
    print(f"[INFO] Database not available: {e}")
    DATABASE_AVAILABLE = False

PORT = int(os.environ.get('PORT', 5000))
DIRECTORY = "."
SESSION_TTL = 86400  # 24 hours in seconds

def create_signed_session():
    """Create a cryptographically signed session token that doesn't need server storage"""
    expiry = int(time.time()) + SESSION_TTL
    secret = os.environ.get('ADMIN_PASSWORD')
    if not secret:
        raise ValueError("ADMIN_PASSWORD environment variable must be set")
    
    # Create payload: expiry timestamp
    payload = str(expiry)
    
    # Create HMAC signature
    signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Combine payload and signature
    token = f"{payload}.{signature}"
    return token

def verify_signed_session(token):
    """Verify a signed session token without server-side storage"""
    try:
        if not token or '.' not in token:
            return False
        
        payload, signature = token.rsplit('.', 1)
        expiry = int(payload)
        
        # Check if expired
        if time.time() > expiry:
            print(f"[AUTH] Token expired: {expiry} < {time.time()}")
            return False
        
        # Verify signature
        secret = os.environ.get('ADMIN_PASSWORD')
        if not secret:
            print(f"[AUTH] ADMIN_PASSWORD not configured")
            return False
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, expected_signature)
        
        if not is_valid:
            print(f"[AUTH] Invalid signature")
        
        return is_valid
    except Exception as e:
        print(f"[AUTH] Token verification error: {e}")
        return False

mimetypes.add_type('text/yaml', '.yml')
mimetypes.add_type('text/yaml', '.yaml')
mimetypes.add_type('application/json', '.json')

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def check_auth(self):
        cookie_header = self.headers.get('Cookie')
        if not cookie_header:
            print(f"[AUTH] No cookie header found")
            return False
        
        c = cookies.SimpleCookie()
        c.load(cookie_header)
        
        if 'admin_session' in c:
            token = c['admin_session'].value
            is_valid = verify_signed_session(token)
            print(f"[AUTH] Session token found, valid: {is_valid}")
            return is_valid
        
        print(f"[AUTH] No admin_session cookie found in: {cookie_header}")
        return False
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        host = self.headers.get('Host', '').lower()
        
        # Domain-based routing for custom domains
        if 'admin.promostack.io' in host and parsed_path.path == '/':
            try:
                with open('admin-simple.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_error(404, "Admin page not found")
                return
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
                return
        
        elif 'dash.promostack.io' in host and parsed_path.path == '/':
            try:
                with open('index.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_error(404, "Frontend page not found")
                return
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
                return
        
        # Legacy /admin path support - redirect to admin.promostack.io
        if parsed_path.path == '/admin/':
            self.send_response(301)
            self.send_header('Location', '/admin')
            self.end_headers()
        elif parsed_path.path == '/admin':
            # Only allow admin access via admin.promostack.io domain
            # Redirect other domains to the proper admin domain
            if 'admin.promostack.io' not in host:
                self.send_response(301)
                self.send_header('Location', 'https://admin.promostack.io')
                self.end_headers()
                return
            
            try:
                with open('admin-simple.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Admin page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path.startswith('/campaign/'):
            try:
                with open('campaign.html', 'r') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except FileNotFoundError:
                self.send_error(404, "Campaign page not found")
            except Exception as e:
                self.send_error(500, f"Server error: {str(e)}")
        
        elif parsed_path.path == '/api/campaigns':
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                db.update_campaign_statuses()
                campaigns = db.get_all_campaigns()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(campaigns).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting campaigns: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submissions' in parsed_path.path:
            # Get campaign submissions - handled below
            pass
        
        elif parsed_path.path.startswith('/api/campaigns/'):
            # Get single campaign by ID
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                campaign = db.get_campaign_by_id(campaign_id)
                
                if campaign:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True, 'campaign': campaign}).encode())
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Campaign not found'}).encode())
            except (IndexError, ValueError):
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Invalid campaign ID'}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submissions' in parsed_path.path:
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                submissions = db.get_campaign_submissions(campaign_id)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(submissions).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error getting submissions: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else:
            super().do_GET()
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/login':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                password = data.get('password', '')
                admin_password = os.environ.get('ADMIN_PASSWORD', '')
                
                if password == admin_password and admin_password:
                    session_token = create_signed_session()
                    
                    # Add Secure flag for HTTPS (Digital Ocean runs on port 8080 with HTTPS)
                    is_production = PORT == 8080 or os.environ.get('APP_URL', '').startswith('https')
                    secure_flag = '; Secure' if is_production else ''
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Set-Cookie', f'admin_session={session_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400{secure_flag}')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode())
                else:
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Invalid password'}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/logout':
            # No server-side cleanup needed with signed cookies
            # Just clear the cookie on the client side
            
            # Add Secure flag for HTTPS (Digital Ocean runs on port 8080 with HTTPS)
            is_production = PORT == 8080 or os.environ.get('APP_URL', '').startswith('https')
            secure_flag = '; Secure' if is_production else ''
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Set-Cookie', f'admin_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_flag}')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif parsed_path.path == '/api/upload-overlay':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            if not OBJECT_STORAGE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Object storage not available'}).encode())
                return
            
            try:
                content_type = self.headers['Content-Type']
                if not content_type.startswith('multipart/form-data'):
                    raise ValueError('Expected multipart/form-data')
                
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        'REQUEST_METHOD': 'POST',
                        'CONTENT_TYPE': self.headers['Content-Type'],
                    }
                )
                
                if 'overlayImage' not in form or not form['overlayImage'].filename:
                    raise ValueError('No overlay image provided')
                
                overlay_file = form['overlayImage']
                filename = overlay_file.filename
                
                # Generate unique filename with timestamp
                import time
                timestamp = int(time.time())
                ext = filename.split('.')[-1] if '.' in filename else 'png'
                overlay_filename = f"overlay_{timestamp}.{ext}"
                
                # Read image data
                image_data = overlay_file.file.read()
                
                # Upload to Spaces
                storage_service = ObjectStorageService()
                overlay_url = storage_service.upload_file(
                    image_data,
                    f'campaigns/overlays/{overlay_filename}'
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'overlay_url': overlay_url
                }).encode())
                
            except Exception as e:
                print(f"[OVERLAY] Upload error: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/upload-template':
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_type = self.headers['Content-Type']
                if not content_type.startswith('multipart/form-data'):
                    raise ValueError('Expected multipart/form-data')
                
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        'REQUEST_METHOD': 'POST',
                        'CONTENT_TYPE': self.headers['Content-Type'],
                    }
                )
                
                name = form.getvalue('name')
                slug = form.getvalue('slug')
                
                import re
                if not slug or not re.match(r'^[a-z0-9-]+$', slug):
                    raise ValueError('Invalid slug: must contain only lowercase letters, numbers, and hyphens')
                
                if '..' in slug or '/' in slug or '\\' in slug:
                    raise ValueError('Invalid slug: path traversal detected')
                
                # Check if template already exists (editing vs creating)
                template_dir = os.path.join('assets', 'templates', slug)
                is_existing_template = os.path.exists(template_dir)
                
                # Check if images are provided (optional for updates, at least one required for new templates)
                has_square_image = 'squareImage' in form and form['squareImage'].filename
                has_story_image = 'storyImage' in form and form['storyImage'].filename
                
                # For new templates, at least one image is required
                if not is_existing_template:
                    if not has_square_image and not has_story_image:
                        raise ValueError('At least one variant (square or portrait) image is required for new templates')
                
                square_coords = {
                    'leftPct': float(form.getvalue('squareLeftPct')),
                    'topPct': float(form.getvalue('squareTopPct')),
                    'widthPct': float(form.getvalue('squareWidthPct')),
                    'heightPct': float(form.getvalue('squareHeightPct')),
                    'hAlign': form.getvalue('squareHAlign'),
                    'vAlign': form.getvalue('squareVAlign')
                }
                
                story_coords = {
                    'leftPct': float(form.getvalue('storyLeftPct')),
                    'topPct': float(form.getvalue('storyTopPct')),
                    'widthPct': float(form.getvalue('storyWidthPct')),
                    'heightPct': float(form.getvalue('storyHeightPct')),
                    'hAlign': form.getvalue('storyHAlign'),
                    'vAlign': form.getvalue('storyVAlign')
                }
                
                square_max_font = int(float(form.getvalue('squareMaxFontPx')))
                story_max_font = int(float(form.getvalue('storyMaxFontPx')))
                
                # Get font colors with defaults
                square_font_color = form.getvalue('squareFontColor') or '#FF273E'
                story_font_color = form.getvalue('storyFontColor') or '#FF273E'
                
                # Check if object storage is available (only on Replit)
                if not OBJECT_STORAGE_AVAILABLE and (has_square_image or has_story_image):
                    raise ValueError('Template uploads are only available on Replit. Please use the Replit admin panel to upload templates.')
                
                # Initialize object storage service (only if available)
                storage_service = ObjectStorageService() if OBJECT_STORAGE_AVAILABLE else None
                image_urls = {}
                
                # Load existing meta.json to preserve all variant data if updating
                # Support both 'imageUrl' (new) and 'image' (legacy) fields
                existing_square_url = None
                existing_story_url = None
                existing_square_data = None
                existing_story_data = None
                if is_existing_template:
                    meta_path = os.path.join(template_dir, 'meta.json')
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r') as f:
                                existing_meta = json.load(f)
                                if 'square' in existing_meta and isinstance(existing_meta['square'], dict):
                                    existing_square_data = existing_meta['square']
                                    # Check both new (imageUrl) and legacy (image) fields
                                    existing_square_url = existing_square_data.get('imageUrl') or existing_square_data.get('image')
                                if 'story' in existing_meta and isinstance(existing_meta['story'], dict):
                                    existing_story_data = existing_meta['story']
                                    # Check both new (imageUrl) and legacy (image) fields  
                                    existing_story_url = existing_story_data.get('imageUrl') or existing_story_data.get('image')
                        except Exception as e:
                            print(f"Warning: Could not load existing meta.json: {e}")
                
                # Upload images to object storage if provided and available
                if has_square_image and storage_service:
                    square_image = form['squareImage']
                    square_data = square_image.file.read()
                    image_urls['square'] = storage_service.upload_file(square_data, f"templates/{slug}/square.png")
                
                if has_story_image and storage_service:
                    story_image = form['storyImage']
                    story_data = story_image.file.read()
                    image_urls['story'] = storage_service.upload_file(story_data, f"templates/{slug}/story.png")
                
                # Create directory for meta.json (keep this local for now)
                os.makedirs(template_dir, exist_ok=True)
                
                # Determine imageUrl: use newly uploaded URL, or preserve existing, or None if not provided
                square_image_url = image_urls.get('square') or existing_square_url
                story_image_url = image_urls.get('story') or existing_story_url
                
                # Build meta.json with object storage URLs for images (only include variants that exist)
                meta = {
                    'name': name
                }
                
                # Add square variant if: newly uploaded, existing URL found, or existing variant data exists
                if square_image_url or has_square_image or existing_square_data:
                    # Build fresh variant dict - never mutate existing_square_data
                    meta['square'] = {
                        'box': square_coords,
                        'maxFontPx': square_max_font,
                        'fontColor': square_font_color,
                        'imageUrl': square_image_url or existing_square_url or f'assets/templates/{slug}/square.png'
                    }
                
                # Add story variant if: newly uploaded, existing URL found, or existing variant data exists
                if story_image_url or has_story_image or existing_story_data:
                    # Build fresh variant dict - never mutate existing_story_data
                    meta['story'] = {
                        'box': story_coords,
                        'maxFontPx': story_max_font,
                        'fontColor': story_font_color,
                        'imageUrl': story_image_url or existing_story_url or f'assets/templates/{slug}/story.png'
                    }
                
                # Validation: ensure at least one variant exists in final meta
                if 'square' not in meta and 'story' not in meta:
                    raise ValueError('Template must have at least one variant (square or portrait)')
                
                # Save meta.json locally
                meta_path = os.path.join(template_dir, 'meta.json')
                with open(meta_path, 'w') as f:
                    json.dump(meta, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Also save meta.json to object storage for persistence (if available)
                if storage_service:
                    meta_json_str = json.dumps(meta, indent=2)
                    storage_service.upload_file(meta_json_str.encode(), f"templates/{slug}/meta.json")
                
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise Exception(f'Index regeneration failed: {result.stderr or result.stdout}')
                
                # CRITICAL: Upload index.json to Spaces so it persists across deployments
                if storage_service:
                    index_path = os.path.join('assets', 'templates', 'index.json')
                    if os.path.exists(index_path):
                        with open(index_path, 'r') as f:
                            index_content = f.read()
                        storage_service.upload_file(index_content.encode(), 'templates/index.json')
                        print(f"[UPLOAD] index.json uploaded to Spaces for persistence")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Template "{name}" uploaded successfully',
                    'slug': slug
                }).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/delete-template':
            print(f"[DELETE] Delete request received")
            if not self.check_auth():
                print(f"[DELETE] Authentication failed - returning 401")
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'Unauthorized - please login again'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                slug = data.get('slug', '')
                
                print(f"[DELETE] Authenticated - attempting to delete template: {slug}")
                
                import re
                if not slug or not re.match(r'^[a-z0-9-]+$', slug):
                    raise ValueError('Invalid slug')
                
                if '..' in slug or '/' in slug or '\\' in slug:
                    raise ValueError('Invalid slug: path traversal detected')
                
                template_dir = os.path.join('assets', 'templates', slug)
                deleted_something = False
                
                # Delete from object storage first (if available) - this is the primary source
                if OBJECT_STORAGE_AVAILABLE:
                    storage_service = ObjectStorageService()
                    storage_service.delete_template(slug)
                    print(f"[DELETE] Template removed from object storage: {slug}")
                    deleted_something = True
                
                # Delete local directory if it exists (optional - may not exist in production)
                import shutil
                if os.path.exists(template_dir):
                    shutil.rmtree(template_dir)
                    print(f"[DELETE] Template directory removed: {template_dir}")
                    deleted_something = True
                else:
                    print(f"[DELETE] No local directory found (normal in production): {template_dir}")
                
                # Make sure we deleted something
                if not deleted_something:
                    raise ValueError(f'Template "{slug}" not found in storage or locally')
                
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise Exception(f'Index regeneration failed: {result.stderr or result.stdout}')
                
                print(f"[DELETE] Index regenerated successfully")
                
                # CRITICAL: Upload index.json to Spaces so deletion persists across deployments
                if OBJECT_STORAGE_AVAILABLE:
                    index_path = os.path.join('assets', 'templates', 'index.json')
                    if os.path.exists(index_path):
                        with open(index_path, 'r') as f:
                            index_content = f.read()
                        storage_service.upload_file(index_content.encode(), 'templates/index.json')
                        print(f"[DELETE] index.json uploaded to Spaces after deletion")
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': f'Template "{slug}" deleted successfully'
                }).encode())
                
                print(f"[DELETE] Success response sent for: {slug}")
                
            except Exception as e:
                print(f"[DELETE] Error during deletion: {str(e)}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/regenerate-index':
            try:
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'success': True,
                        'message': 'Index regenerated successfully',
                        'output': result.stdout
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'success': False,
                        'error': result.stderr or 'Failed to regenerate index'
                    }
                    self.wfile.write(json.dumps(response).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
        
        elif parsed_path.path == '/api/telegram-webhook':
            if not TELEGRAM_BOT_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Telegram bot not available'}).encode())
                return
            
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
                
                if not bot_token:
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Bot token not configured'}).encode())
                    return
                
                # Parse JSON from webhook
                webhook_data = json.loads(post_data.decode('utf-8'))
                
                # Handle the webhook
                result = telegram_bot.handle_telegram_webhook(webhook_data, bot_token)
                
                # Telegram expects 200 OK even if we couldn't process the command
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except Exception as e:
                print(f"[TELEGRAM] Webhook error: {str(e)}")
                # Still send 200 to Telegram so it doesn't retry
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path == '/api/campaigns':
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                campaign_id = db.create_campaign(
                    title=data['title'],
                    description=data.get('description', ''),
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    prize=data.get('prize', ''),
                    platforms=json.dumps(data.get('platforms', [])),
                    overlay_url=data.get('overlay_url')
                )
                
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'id': campaign_id}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error creating campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif parsed_path.path.startswith('/api/campaigns/') and '/submit' in parsed_path.path:
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                submission_id = db.create_submission(
                    campaign_id=campaign_id,
                    email=data['email'],
                    instagram_url=data.get('instagram_url', ''),
                    twitter_url=data.get('twitter_url', ''),
                    facebook_url=data.get('facebook_url', '')
                )
                
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'id': submission_id}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error creating submission: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else:
            self.send_error(404, "Not Found")
    
    def do_PUT(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path.startswith('/api/campaigns/'):
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                db.update_campaign(
                    campaign_id=campaign_id,
                    title=data['title'],
                    description=data.get('description', ''),
                    start_date=data['start_date'],
                    end_date=data['end_date'],
                    prize=data.get('prize', ''),
                    platforms=json.dumps(data.get('platforms', [])),
                    overlay_url=data.get('overlay_url')
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error updating campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")
    
    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path.startswith('/api/campaigns/'):
            if not DATABASE_AVAILABLE:
                self.send_response(503)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Database not available'}).encode())
                return
            
            if not self.check_auth():
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return
            
            try:
                campaign_id = int(parsed_path.path.split('/')[3])
                db.delete_campaign(campaign_id)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            except Exception as e:
                print(f"[CAMPAIGNS] Error deleting campaign: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_error(404, "Not Found")

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Server running at http://0.0.0.0:{PORT}/")
        print(f"Serving files from {os.path.abspath(DIRECTORY)}")
        print(f"API endpoints:")
        print(f"  POST /api/login")
        print(f"  POST /api/logout")
        print(f"  POST /api/upload-template (requires auth)")
        print(f"  POST /api/delete-template (requires auth)")
        print(f"  POST /api/regenerate-index")
        print(f"  POST /api/telegram-webhook")
        httpd.serve_forever()
