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
import fcntl

PORT = int(os.environ.get('PORT', 5000))
DIRECTORY = "."
SESSIONS_FILE = 'sessions.json'
SESSION_TTL = 86400  # 24 hours in seconds

def _atomic_session_operation(operation, token=None):
    """Atomic read-modify-write for session operations with exclusive lock"""
    try:
        # Create file if it doesn't exist
        if not os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'w') as f:
                json.dump({}, f)
        
        # Atomic read-modify-write with exclusive lock
        with open(SESSIONS_FILE, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                sessions = json.load(f)
            except:
                sessions = {}
            
            # Remove expired sessions
            now = time.time()
            sessions = {t: exp for t, exp in sessions.items() if exp > now}
            
            # Perform requested operation
            result = False
            if operation == 'add' and token:
                sessions[token] = now + SESSION_TTL
                result = True
            elif operation == 'remove' and token:
                if token in sessions:
                    del sessions[token]
                    result = True
            elif operation == 'check' and token:
                result = token in sessions and sessions[token] > now
            
            # Write back atomically
            f.seek(0)
            f.truncate()
            json.dump(sessions, f)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            return (result, len(sessions))
    except Exception as e:
        print(f"[SESSION] Error in atomic operation '{operation}': {e}")
        return (False, 0)

def add_session(token):
    """Add a new session token atomically"""
    _atomic_session_operation('add', token)

def remove_session(token):
    """Remove a session token atomically"""
    _atomic_session_operation('remove', token)

def is_valid_session(token):
    """Check if a session token is valid atomically"""
    result, _ = _atomic_session_operation('check', token)
    return result

def get_session_count():
    """Get current session count"""
    _, count = _atomic_session_operation('check', None)
    return count

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
            is_valid = is_valid_session(token)
            count = get_session_count()
            print(f"[AUTH] Session token found, valid: {is_valid}, active sessions: {count}")
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
                    session_token = secrets.token_urlsafe(32)
                    add_session(session_token)
                    
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
            cookie_header = self.headers.get('Cookie')
            if cookie_header:
                c = cookies.SimpleCookie()
                c.load(cookie_header)
                if 'admin_session' in c:
                    token = c['admin_session'].value
                    remove_session(token)
            
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
                
                # Create directory if it doesn't exist
                os.makedirs(template_dir, exist_ok=True)
                
                # Only save images if they were provided
                if has_square_image:
                    square_image = form['squareImage']
                    square_path = os.path.join(template_dir, 'square.png')
                    with open(square_path, 'wb') as f:
                        f.write(square_image.file.read())
                
                if has_story_image:
                    story_image = form['storyImage']
                    story_path = os.path.join(template_dir, 'story.png')
                    with open(story_path, 'wb') as f:
                        f.write(story_image.file.read())
                
                meta = {
                    'name': name,
                    'square': {
                        'box': square_coords,
                        'maxFontPx': square_max_font,
                        'fontColor': square_font_color
                    },
                    'story': {
                        'box': story_coords,
                        'maxFontPx': story_max_font,
                        'fontColor': story_font_color
                    }
                }
                
                meta_path = os.path.join(template_dir, 'meta.json')
                with open(meta_path, 'w') as f:
                    json.dump(meta, f, indent=2)
                
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
