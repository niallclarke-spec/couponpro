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
from object_storage import ObjectStorageService

# Load environment variables from .env file
load_dotenv()

PORT = int(os.environ.get('PORT', 5000))
DIRECTORY = "."
SESSION_TTL = 86400  # 24 hours in seconds

def create_signed_session():
    """Create a cryptographically signed session token that doesn't need server storage"""
    expiry = int(time.time()) + SESSION_TTL
    secret = os.environ.get('ADMIN_PASSWORD', 'fallback-secret')
    
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
        secret = os.environ.get('ADMIN_PASSWORD', 'fallback-secret')
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
        
        if parsed_path.path == '/admin/':
            self.send_response(301)
            self.send_header('Location', '/admin')
            self.end_headers()
        elif parsed_path.path == '/admin':
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
                
                # Check if images are provided (optional for updates, required for new templates)
                has_square_image = 'squareImage' in form and form['squareImage'].filename
                has_story_image = 'storyImage' in form and form['storyImage'].filename
                
                # For new templates, both images are required
                if not is_existing_template:
                    if not has_square_image or not has_story_image:
                        raise ValueError('Both square and story images are required for new templates')
                
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
                
                # Initialize object storage service
                storage_service = ObjectStorageService()
                image_urls = {}
                
                # Load existing meta.json to preserve imageUrl values if updating
                existing_square_url = None
                existing_story_url = None
                if is_existing_template:
                    meta_path = os.path.join(template_dir, 'meta.json')
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r') as f:
                                existing_meta = json.load(f)
                                if 'square' in existing_meta and isinstance(existing_meta['square'], dict):
                                    existing_square_url = existing_meta['square'].get('imageUrl')
                                if 'story' in existing_meta and isinstance(existing_meta['story'], dict):
                                    existing_story_url = existing_meta['story'].get('imageUrl')
                        except Exception as e:
                            print(f"Warning: Could not load existing meta.json: {e}")
                
                # Upload images to object storage if provided
                if has_square_image:
                    square_image = form['squareImage']
                    square_data = square_image.file.read()
                    image_urls['square'] = storage_service.upload_file(square_data, f"templates/{slug}/square.png")
                
                if has_story_image:
                    story_image = form['storyImage']
                    story_data = story_image.file.read()
                    image_urls['story'] = storage_service.upload_file(story_data, f"templates/{slug}/story.png")
                
                # Create directory for meta.json (keep this local for now)
                os.makedirs(template_dir, exist_ok=True)
                
                # Determine imageUrl: use newly uploaded URL, or preserve existing, or fallback to local path
                square_image_url = image_urls.get('square') or existing_square_url or f'assets/templates/{slug}/square.png'
                story_image_url = image_urls.get('story') or existing_story_url or f'assets/templates/{slug}/story.png'
                
                # Build meta.json with object storage URLs for images
                meta = {
                    'name': name,
                    'square': {
                        'box': square_coords,
                        'maxFontPx': square_max_font,
                        'fontColor': square_font_color,
                        'imageUrl': square_image_url
                    },
                    'story': {
                        'box': story_coords,
                        'maxFontPx': story_max_font,
                        'fontColor': story_font_color,
                        'imageUrl': story_image_url
                    }
                }
                
                # Save meta.json locally
                meta_path = os.path.join(template_dir, 'meta.json')
                with open(meta_path, 'w') as f:
                    json.dump(meta, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Also save meta.json to object storage for persistence
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
                
                if not os.path.exists(template_dir):
                    raise ValueError(f'Template "{slug}" not found')
                
                # Delete from object storage first
                storage_service = ObjectStorageService()
                storage_service.delete_template(slug)
                print(f"[DELETE] Template removed from object storage: {slug}")
                
                # Delete local directory
                import shutil
                shutil.rmtree(template_dir)
                print(f"[DELETE] Template directory removed: {template_dir}")
                
                result = subprocess.run(
                    ['python3', 'regenerate_index.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise Exception(f'Index regeneration failed: {result.stderr or result.stdout}')
                
                print(f"[DELETE] Index regenerated successfully")
                
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
        httpd.serve_forever()
