"""
Page handlers for serving HTML pages.

Extracted from server.py - these handle serving HTML pages with proper
authentication, redirects, and template injection.
"""
from core.config import Config
from core.host_context import HostContext, HostType

from core.logging import get_logger
logger = get_logger(__name__)


def serve_login(handler):
    """
    GET /login - Serve login page with Clerk publishable key injection.
    """
    try:
        with open('login.html', 'r') as f:
            content = f.read()
        clerk_key = Config.get_clerk_publishable_key() or ''
        content = content.replace('{{CLERK_PUBLISHABLE_KEY}}', clerk_key)
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Login page not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")


def serve_admin(handler, host_context: HostContext):
    """
    GET /admin - Serve admin dashboard with server-side auth protection.
    
    - On dash subdomain in prod: redirect to admin.promostack.io
    - Requires authentication and admin email
    - Returns 403 with access denied page if not admin
    """
    from auth.clerk_auth import get_auth_user_from_request, is_admin_email
    from urllib.parse import unquote
    
    if not host_context.is_dev and host_context.host_type == HostType.DASH:
        handler.send_response(302)
        handler.send_header('Location', 'https://admin.promostack.io/admin')
        handler.end_headers()
        return
    
    auth_user = get_auth_user_from_request(handler)
    
    if not auth_user:
        handler.send_response(302)
        handler.send_header('Location', '/login')
        handler.end_headers()
        return
    
    user_email = auth_user.get('email')
    if not user_email:
        user_email = handler.headers.get('X-Clerk-User-Email', '')
    if not user_email:
        cookie_header = handler.headers.get('Cookie', '')
        if 'clerk_user_email=' in cookie_header:
            for part in cookie_header.split(';'):
                part = part.strip()
                if part.startswith('clerk_user_email='):
                    user_email = unquote(part[17:])
                    break
    
    if not is_admin_email(user_email):
        handler.send_response(403)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        access_denied_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Access Denied | PromoStack</title>
    <style>
        body {{ font-family: Inter, sans-serif; background: #091128; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .container {{ text-align: center; padding: 40px; }}
        h1 {{ color: #ef4444; margin-bottom: 16px; }}
        p {{ color: #94a3b8; margin-bottom: 24px; }}
        a {{ color: #4f46e5; text-decoration: none; }}
        .email {{ color: #64748b; font-size: 14px; margin-top: 16px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Access Denied</h1>
        <p>You don't have permission to access the admin dashboard.</p>
        <a href="/login?signed_out=1">Sign out and use a different account</a>
        <p class="email">Logged in as: {user_email or 'Unknown'}</p>
    </div>
</body>
</html>'''
        handler.wfile.write(access_denied_html.encode('utf-8'))
        return
    
    try:
        with open('admin.html', 'r') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Admin page not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")


def serve_app(handler, host_context: HostContext):
    """
    GET /app - Serve client dashboard.
    
    - On admin subdomain in prod: redirect to dash.promostack.io
    """
    if not host_context.is_dev and host_context.host_type == HostType.ADMIN:
        handler.send_response(302)
        handler.send_header('Location', 'https://dash.promostack.io/app')
        handler.end_headers()
        return
    
    try:
        with open('app.html', 'r') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Client dashboard not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")


def serve_setup(handler):
    """
    GET /setup - Serve setup page.
    """
    try:
        with open('setup.html', 'r') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Setup page not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")


def serve_coupon(handler):
    """
    GET /coupon - Serve coupon/index page.
    """
    try:
        with open('index.html', 'r') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Coupon page not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")


def serve_campaign(handler):
    """
    GET /campaign/<id> - Serve campaign page.
    """
    try:
        with open('campaign.html', 'r') as f:
            content = f.read()
        
        handler.send_response(200)
        handler.send_header('Content-type', 'text/html; charset=utf-8')
        handler.end_headers()
        handler.wfile.write(content.encode('utf-8'))
    except FileNotFoundError:
        handler.send_error(404, "Campaign page not found")
    except Exception as e:
        handler.send_error(500, f"Server error: {str(e)}")
