"""
HTTP response helpers for server.py
Preserves existing response patterns: headers, status codes, JSON shape.
NO side effects at import time.
"""
import json
import mimetypes
import os


def send_json(handler, data: dict, status: int = 200):
    """
    Send a JSON response.
    
    Preserves existing pattern:
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    Usage:
        send_json(self, {'authenticated': True})
        send_json(self, {'error': 'Not found'}, status=404)
    """
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def send_error(handler, message: str, status: int = 500):
    """
    Send a JSON error response.
    
    Preserves existing pattern:
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': str(e)}).encode())
    
    Usage:
        send_error(self, 'Database not available', status=503)
        send_error(self, str(e), status=500)
    """
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'error': message}).encode())


def send_html(handler, content: str, status: int = 200):
    """
    Send an HTML response.
    
    Preserves existing pattern:
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    Usage:
        with open('admin.html', 'r') as f:
            send_html(self, f.read())
    """
    handler.send_response(status)
    handler.send_header('Content-type', 'text/html; charset=utf-8')
    handler.end_headers()
    handler.wfile.write(content.encode('utf-8'))


def send_file(handler, file_path: str, content_type: str | None = None):
    """
    Send a file response with appropriate content type.
    
    Uses mimetypes to guess content type if not provided.
    Returns False if file not found, True on success.
    
    Usage:
        if not send_file(self, 'assets/image.png'):
            send_error(self, 'File not found', status=404)
    """
    if not os.path.isfile(file_path):
        return False
    
    # Guess content type if not provided
    if content_type is None:
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', content_type)
        handler.send_header('Content-Length', str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
        return True
    except Exception:
        return False


def send_redirect(handler, location: str, permanent: bool = False):
    """
    Send an HTTP redirect.
    
    Preserves existing pattern:
        self.send_response(301)
        self.send_header('Location', '/admin')
        self.end_headers()
    
    Usage:
        send_redirect(self, '/admin', permanent=True)
        send_redirect(self, 'https://admin.promostack.io')
    """
    status = 301 if permanent else 302
    handler.send_response(status)
    handler.send_header('Location', location)
    handler.end_headers()
