"""
Coupon domain handlers.

Extracted from server.py - these handle campaign, template, broadcast, and coupon-related API endpoints.
"""
import json
import traceback
import time
import os
import subprocess
from urllib.parse import urlparse, parse_qs

from utils.multipart import parse_multipart_formdata

from core.config import Config

from core.logging import get_logger
logger = get_logger(__name__)


def handle_campaigns_list(handler):
    """GET /api/campaigns"""
    import server
    
    try:
        server.db.update_campaign_statuses()
        campaigns = server.db.get_all_campaigns(tenant_id=handler.tenant_id)
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(campaigns).encode())
    except Exception as e:
        logger.exception("Error getting campaigns")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_campaign_by_id(handler):
    """GET /api/campaigns/<id>"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        campaign_id = int(parsed_path.path.split('/')[3])
        campaign = server.db.get_campaign_by_id(campaign_id, tenant_id=handler.tenant_id)
        
        if campaign:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': True, 'campaign': campaign}).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Campaign not found'}).encode())
    except (IndexError, ValueError):
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Invalid campaign ID'}).encode())
    except Exception as e:
        logger.exception("Error getting campaign")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_campaign_submissions(handler):
    """GET /api/campaigns/<id>/submissions"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        campaign_id = int(parsed_path.path.split('/')[3])
        submissions = server.db.get_campaign_submissions(campaign_id, tenant_id=handler.tenant_id)
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(submissions).encode())
    except Exception as e:
        logger.exception("Error getting submissions")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_bot_stats(handler):
    """GET /api/bot-stats"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        days_param = query_params.get('days', ['30'])[0]
        template = query_params.get('template', [None])[0]
        
        if template in [None, '', 'null', 'all']:
            template = None
        
        if days_param in ['today', 'yesterday']:
            days = days_param
        else:
            days = int(days_param)
        
        stats = server.db.get_bot_stats(days, template_filter=template, tenant_id=handler.tenant_id)
        
        if stats:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(stats).encode())
        else:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'total_uses': 0,
                'successful_uses': 0,
                'success_rate': 0,
                'unique_users': 0,
                'popular_templates': [],
                'popular_coupons': [],
                'errors': [],
                'daily_usage': []
            }).encode())
    except Exception as e:
        logger.exception("Error getting bot stats")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_bot_users(handler):
    """GET /api/bot-users"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        limit = int(query_params.get('limit', ['100'])[0])
        offset = int(query_params.get('offset', ['0'])[0])
        
        result = server.db.get_all_bot_users(limit=limit, offset=offset, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
    except Exception as e:
        logger.exception("Error getting bot users")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_broadcast_status(handler):
    """GET /api/broadcast-status/<id>"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        job_id = int(parsed_path.path.split('/')[-1])
        job = server.db.get_broadcast_job(job_id, tenant_id=handler.tenant_id)
        
        if job:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps(job).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'error': 'Job not found'}).encode())
    except Exception as e:
        logger.exception("Error getting job status")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_broadcast_jobs(handler):
    """GET /api/broadcast-jobs"""
    import server
    
    try:
        jobs = server.db.get_recent_broadcast_jobs(limit=20, tenant_id=handler.tenant_id)
        user_count = server.db.get_bot_user_count(days=30, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'jobs': jobs,
            'active_users': user_count
        }).encode())
    except Exception as e:
        logger.exception("Error getting broadcast jobs")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_user_activity(handler):
    """GET /api/user-activity/<id>"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        chat_id = int(parsed_path.path.split('/')[-1])
        
        user = server.db.get_bot_user(chat_id, tenant_id=handler.tenant_id)
        history = server.db.get_user_activity_history(chat_id, limit=100, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'user': user,
            'history': history
        }).encode())
    except Exception as e:
        logger.exception("Error getting user activity")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_invalid_coupons(handler):
    """GET /api/invalid-coupons"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        query_params = parse_qs(parsed_path.query)
        limit = int(query_params.get('limit', ['100'])[0])
        offset = int(query_params.get('offset', ['0'])[0])
        template_filter = query_params.get('template', [None])[0]
        days_param = query_params.get('days', [None])[0]
        
        days = None
        if days_param:
            try:
                days = int(days_param)
                if days < 1 or days > 365:
                    days = 30
            except (ValueError, TypeError):
                days = 30
        
        result = server.db.get_invalid_coupon_attempts(
            limit=limit, 
            offset=offset, 
            template_filter=template_filter,
            days=days,
            tenant_id=handler.tenant_id
        )
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
    except Exception as e:
        logger.exception("Error getting invalid coupons")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_validate_coupon(handler):
    """POST /api/validate-coupon"""
    import server
    
    if not server.COUPON_VALIDATOR_AVAILABLE:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'valid': False,
            'message': 'Coupon validation service unavailable'
        }).encode())
        return
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        coupon_code = data.get('coupon_code', '').strip()
        
        if not coupon_code:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'valid': False,
                'message': 'Coupon code is required'
            }).encode())
            return
        
        result = server.coupon_validator.validate_coupon(coupon_code)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'valid': False,
            'message': 'Invalid request format'
        }).encode())
    except Exception as e:
        logger.exception("Validation error")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'valid': False,
            'message': 'Server error during validation'
        }).encode())


def handle_campaigns_create(handler):
    """POST /api/campaigns"""
    import server
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        campaign = server.db.create_campaign(data, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': True, 'campaign': campaign}).encode())
    except Exception as e:
        logger.exception("Error creating campaign")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_campaign_submit(handler):
    """POST /api/campaigns/<id>/submit"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        campaign_id = int(parsed_path.path.split('/')[3])
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        result = server.db.submit_to_campaign(campaign_id, data, tenant_id=handler.tenant_id)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
    except Exception as e:
        logger.exception("Error submitting to campaign")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_campaign_update(handler):
    """POST /api/campaigns/<id>/update"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        campaign_id = int(parsed_path.path.split('/')[3])
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        campaign = server.db.update_campaign(campaign_id, data, tenant_id=handler.tenant_id)
        
        if campaign:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': True, 'campaign': campaign}).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Campaign not found'}).encode())
    except Exception as e:
        logger.exception("Error updating campaign")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_campaign_delete(handler):
    """POST /api/campaigns/<id>/delete"""
    import server
    parsed_path = urlparse(handler.path)
    
    try:
        campaign_id = int(parsed_path.path.split('/')[3])
        
        result = server.db.delete_campaign(campaign_id, tenant_id=handler.tenant_id)
        
        if result:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': True}).encode())
        else:
            handler.send_response(404)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({'success': False, 'error': 'Campaign not found'}).encode())
    except Exception as e:
        logger.exception("Error deleting campaign")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_broadcast(handler):
    """POST /api/broadcast"""
    import server
    
    if not server.TELEGRAM_BOT_AVAILABLE:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error': 'Telegram bot not available'
        }).encode())
        return
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        message = data.get('message', '').strip()
        days = int(data.get('days', 30))
        
        if not message:
            handler.send_response(400)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': False,
                'error': 'Message is required'
            }).encode())
            return
        
        users = server.db.get_active_bot_users(days, tenant_id=handler.tenant_id)
        
        if not users:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'sent': 0,
                'failed': 0,
                'total': 0,
                'message': 'No active users found'
            }).encode())
            return
        
        result = server.telegram_bot.send_broadcast(users, message)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(result).encode())
        
    except json.JSONDecodeError:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error': 'Invalid request format'
        }).encode())
    except Exception as e:
        logger.exception("Broadcast error")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': False,
            'error': str(e)
        }).encode())


def handle_upload_overlay(handler):
    """POST /api/upload-overlay"""
    import server
    from object_storage import ObjectStorageService
    
    if not server.OBJECT_STORAGE_AVAILABLE:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': 'Object storage not available'}).encode())
        return
    
    try:
        content_type = handler.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            raise ValueError('Expected multipart/form-data')
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length) if content_length else b''
        fields, files = parse_multipart_formdata(content_type, body)
        
        if 'overlayImage' not in files or not files['overlayImage'].get('filename'):
            raise ValueError('No overlay image provided')
        
        overlay_file = files['overlayImage']
        filename = overlay_file['filename']
        
        timestamp = int(time.time())
        ext = filename.split('.')[-1] if '.' in filename else 'png'
        overlay_filename = f"overlay_{timestamp}.{ext}"
        
        image_data = overlay_file['data']
        
        storage_service = ObjectStorageService()
        overlay_url = storage_service.upload_file(
            image_data,
            f'campaigns/overlays/{overlay_filename}'
        )
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'overlay_url': overlay_url
        }).encode())
        
    except Exception as e:
        logger.exception("Upload error")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_upload_template(handler):
    """POST /api/upload-template"""
    import server
    import re
    import urllib.request
    import urllib.error
    
    try:
        content_type = handler.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            raise ValueError('Expected multipart/form-data')
        
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length) if content_length else b''
        fields, files = parse_multipart_formdata(content_type, body)
        
        name = fields.get('name')
        slug = fields.get('slug')
        
        logger.info(f"Received slug from client: '{slug}'")
        logger.info(f"Received name from client: '{name}'")
        
        if not slug or not re.match(r'^[a-z0-9-]+$', slug):
            raise ValueError('Invalid slug: must contain only lowercase letters, numbers, and hyphens')
        
        if '..' in slug or '/' in slug or '\\' in slug:
            raise ValueError('Invalid slug: path traversal detected')
        
        is_editing = fields.get('isEditing') == 'true'
        logger.info(f"isEditing flag: {is_editing}")
        
        template_dir = os.path.join('assets', 'templates', slug)
        is_existing_template = os.path.exists(template_dir)
        
        if not is_existing_template and server.OBJECT_STORAGE_AVAILABLE:
            try:
                spaces_bucket = Config.get_spaces_bucket()
                spaces_region = Config.get_spaces_region()
                cdn_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
                req = urllib.request.Request(cdn_url, method='HEAD')
                urllib.request.urlopen(req, timeout=5)
                is_existing_template = True
                logger.info(f"Template '{slug}' exists in Spaces - allowing edit without images")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    logger.info(f"Template '{slug}' confirmed not in Spaces (404) - allowing upload")
                else:
                    logger.info(f"Template '{slug}' - Spaces check got HTTP {e.code}, allowing upload to proceed")
            except Exception as e:
                logger.warning(f"Spaces check error for '{slug}': {e} - allowing upload to proceed")
        
        if not is_editing and is_existing_template:
            error_msg = f"Template with slug '{slug}' already exists! Click 'New Template' to clear the form or edit the existing template instead."
            logger.info(f"REJECTED: {error_msg}")
            raise ValueError(error_msg)
        
        has_square_image = 'squareImage' in files and files['squareImage'].get('filename')
        has_story_image = 'storyImage' in files and files['storyImage'].get('filename')
        
        if not is_existing_template:
            if not has_square_image and not has_story_image:
                raise ValueError('At least one variant (square or portrait) image is required for new templates')
        
        square_coords = {
            'leftPct': float(fields.get('squareLeftPct')),
            'topPct': float(fields.get('squareTopPct')),
            'widthPct': float(fields.get('squareWidthPct')),
            'heightPct': float(fields.get('squareHeightPct')),
            'hAlign': fields.get('squareHAlign'),
            'vAlign': fields.get('squareVAlign')
        }
        
        story_coords = {
            'leftPct': float(fields.get('storyLeftPct')),
            'topPct': float(fields.get('storyTopPct')),
            'widthPct': float(fields.get('storyWidthPct')),
            'heightPct': float(fields.get('storyHeightPct')),
            'hAlign': fields.get('storyHAlign'),
            'vAlign': fields.get('storyVAlign')
        }
        
        square_max_font = int(float(fields.get('squareMaxFontPx')))
        story_max_font = int(float(fields.get('storyMaxFontPx')))
        
        square_font_color = fields.get('squareFontColor') or '#FF273E'
        story_font_color = fields.get('storyFontColor') or '#FF273E'
        
        if not server.OBJECT_STORAGE_AVAILABLE and (has_square_image or has_story_image):
            raise ValueError('Template uploads are only available on Replit. Please use the Replit admin panel to upload templates.')
        
        from object_storage import ObjectStorageService
        storage_service = ObjectStorageService() if server.OBJECT_STORAGE_AVAILABLE else None
        image_urls = {}
        
        existing_square_url = None
        existing_story_url = None
        existing_square_data = None
        existing_story_data = None
        existing_meta = None
        if is_existing_template:
            meta_path = os.path.join(template_dir, 'meta.json')
            
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r') as f:
                        existing_meta = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load local meta.json: {e}")
            
            if not existing_meta and server.OBJECT_STORAGE_AVAILABLE:
                try:
                    spaces_bucket = Config.get_spaces_bucket()
                    spaces_region = Config.get_spaces_region()
                    meta_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
                    response = urllib.request.urlopen(meta_url, timeout=5)
                    existing_meta = json.loads(response.read().decode('utf-8'))
                    logger.info(f"Loaded existing meta.json from Spaces for '{slug}'")
                except Exception as e:
                    logger.warning(f"Could not load meta.json from Spaces: {e}")
            
            if existing_meta:
                if 'square' in existing_meta and isinstance(existing_meta['square'], dict):
                    existing_square_data = existing_meta['square']
                    existing_square_url = existing_square_data.get('imageUrl') or existing_square_data.get('image')
                if 'story' in existing_meta and isinstance(existing_meta['story'], dict):
                    existing_story_data = existing_meta['story']
                    existing_story_url = existing_story_data.get('imageUrl') or existing_story_data.get('image')
        
        if has_square_image and storage_service:
            square_data = files['squareImage']['data']
            image_urls['square'] = storage_service.upload_file(square_data, f"templates/{slug}/square.png")
        
        if has_story_image and storage_service:
            story_data = files['storyImage']['data']
            image_urls['story'] = storage_service.upload_file(story_data, f"templates/{slug}/story.png")
        
        os.makedirs(template_dir, exist_ok=True)
        
        square_image_url = image_urls.get('square') or existing_square_url
        story_image_url = image_urls.get('story') or existing_story_url
        
        existing_telegram_enabled = existing_meta.get('telegramEnabled', True) if existing_meta else True
        
        meta = {
            'name': name,
            'telegramEnabled': existing_telegram_enabled
        }
        
        if square_image_url or has_square_image or existing_square_data:
            meta['square'] = {
                'box': square_coords,
                'maxFontPx': square_max_font,
                'fontColor': square_font_color,
                'imageUrl': square_image_url or existing_square_url or f'assets/templates/{slug}/square.png'
            }
        
        if story_image_url or has_story_image or existing_story_data:
            meta['story'] = {
                'box': story_coords,
                'maxFontPx': story_max_font,
                'fontColor': story_font_color,
                'imageUrl': story_image_url or existing_story_url or f'assets/templates/{slug}/story.png'
            }
        
        if 'square' not in meta and 'story' not in meta:
            raise ValueError('Template must have at least one variant (square or portrait)')
        
        meta_path = os.path.join(template_dir, 'meta.json')
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
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
        
        if storage_service:
            index_path = os.path.join('assets', 'templates', 'index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r') as f:
                    index_content = f.read()
                storage_service.upload_file(index_content.encode(), 'templates/index.json')
                logger.info("index.json uploaded to Spaces for persistence")
        
        if server.TELEGRAM_BOT_AVAILABLE:
            server.telegram_bot.INDEX_CACHE['data'] = None
            server.telegram_bot.INDEX_CACHE['expires_at'] = 0
            logger.info("Telegram cache cleared - template available immediately")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f'Template "{name}" uploaded successfully',
            'slug': slug
        }).encode())
        
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_delete_template(handler):
    """POST /api/delete-template"""
    import server
    import re
    import shutil
    
    logger.info("Delete request received")
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        slug = data.get('slug', '')
        
        logger.info(f"Authenticated - attempting to delete template: {slug}")
        
        if not slug or not re.match(r'^[a-z0-9-]+$', slug):
            raise ValueError('Invalid slug')
        
        if '..' in slug or '/' in slug or '\\' in slug:
            raise ValueError('Invalid slug: path traversal detected')
        
        template_dir = os.path.join('assets', 'templates', slug)
        deleted_something = False
        
        if server.OBJECT_STORAGE_AVAILABLE:
            from object_storage import ObjectStorageService
            storage_service = ObjectStorageService()
            storage_service.delete_template(slug)
            logger.info(f"Template removed from object storage: {slug}")
            deleted_something = True
        
        if os.path.exists(template_dir):
            shutil.rmtree(template_dir)
            logger.info(f"Template directory removed: {template_dir}")
            deleted_something = True
        else:
            logger.info(f"No local directory found (normal in production): {template_dir}")
        
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
        
        logger.info("Index regenerated successfully")
        
        if server.OBJECT_STORAGE_AVAILABLE:
            from object_storage import ObjectStorageService
            storage_service = ObjectStorageService()
            index_path = os.path.join('assets', 'templates', 'index.json')
            if os.path.exists(index_path):
                with open(index_path, 'r') as f:
                    index_content = f.read()
                storage_service.upload_file(index_content.encode(), 'templates/index.json')
                logger.info("index.json uploaded to Spaces after deletion")
        
        if server.TELEGRAM_BOT_AVAILABLE:
            server.telegram_bot.INDEX_CACHE['data'] = None
            server.telegram_bot.INDEX_CACHE['expires_at'] = 0
            logger.info("Telegram cache cleared - template removed immediately")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f'Template "{slug}" deleted successfully'
        }).encode())
        
        logger.info(f"Success response sent for: {slug}")
        
    except Exception as e:
        logger.exception("Error during deletion")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_toggle_telegram_template(handler):
    """POST /api/toggle-telegram-template"""
    import server
    import urllib.request
    
    try:
        content_length = int(handler.headers['Content-Length'])
        post_data = handler.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        slug = data.get('slug')
        enabled = data.get('enabled', True)
        
        if not slug:
            raise ValueError('Template slug is required')
        
        logger.info(f"Toggling template '{slug}' to {'enabled' if enabled else 'disabled'}")
        
        spaces_bucket = Config.get_spaces_bucket()
        spaces_region = Config.get_spaces_region()
        meta_url = f"https://{spaces_bucket}.{spaces_region}.cdn.digitaloceanspaces.com/templates/{slug}/meta.json"
        
        try:
            response = urllib.request.urlopen(meta_url, timeout=5)
            meta = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            raise ValueError(f'Could not load template metadata: {e}')
        
        meta['telegramEnabled'] = enabled
        
        if server.OBJECT_STORAGE_AVAILABLE:
            from object_storage import ObjectStorageService
            storage_service = ObjectStorageService()
            meta_json_str = json.dumps(meta, indent=2)
            storage_service.upload_file(meta_json_str.encode(), f"templates/{slug}/meta.json")
            logger.info(f"Updated meta.json for '{slug}' in Spaces")
        
        template_dir = os.path.join('assets', 'templates', slug)
        if os.path.exists(template_dir):
            meta_path = os.path.join(template_dir, 'meta.json')
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
        
        try:
            result = subprocess.run(
                ['python3', 'regenerate_index.py'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.warning(f"Index regeneration failed: {result.stderr}")
            else:
                logger.info("Index regenerated successfully")
                
                if server.OBJECT_STORAGE_AVAILABLE:
                    from object_storage import ObjectStorageService
                    storage_service = ObjectStorageService()
                    index_path = os.path.join('assets', 'templates', 'index.json')
                    if os.path.exists(index_path):
                        with open(index_path, 'r') as f:
                            index_content = f.read()
                        storage_service.upload_file(index_content.encode(), 'templates/index.json')
                        logger.info("Index.json uploaded to Spaces")
        except Exception as e:
            logger.warning(f"Index update failed: {e}")
        
        if server.TELEGRAM_BOT_AVAILABLE:
            server.telegram_bot.INDEX_CACHE['data'] = None
            server.telegram_bot.INDEX_CACHE['expires_at'] = 0
            logger.info("Telegram cache cleared - visibility change applied immediately")
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({
            'success': True,
            'message': f"Template '{slug}' {'enabled' if enabled else 'disabled'} for Telegram"
        }).encode())
        
    except Exception as e:
        logger.exception("Error toggling template")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_clear_telegram_cache(handler):
    """POST /api/clear-telegram-cache"""
    import server
    
    try:
        if server.TELEGRAM_BOT_AVAILABLE:
            server.telegram_bot.INDEX_CACHE['data'] = None
            server.telegram_bot.INDEX_CACHE['expires_at'] = 0
            logger.info("Telegram template cache cleared")
            
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': True,
                'message': 'Telegram cache cleared - new templates available immediately'
            }).encode())
        else:
            handler.send_response(503)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            handler.wfile.write(json.dumps({
                'success': False,
                'error': 'Telegram bot not available'
            }).encode())
            
    except Exception as e:
        logger.exception("Error clearing cache")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())


def handle_regenerate_index(handler):
    """POST /api/regenerate-index"""
    try:
        result = subprocess.run(
            ['python3', 'regenerate_index.py'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            handler.send_response(200)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            response = {
                'success': True,
                'message': 'Index regenerated successfully',
                'output': result.stdout
            }
            handler.wfile.write(json.dumps(response).encode())
        else:
            handler.send_response(500)
            handler.send_header('Content-type', 'application/json')
            handler.end_headers()
            response = {
                'success': False,
                'error': result.stderr or 'Failed to regenerate index'
            }
            handler.wfile.write(json.dumps(response).encode())
    except Exception as e:
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        response = {'success': False, 'error': str(e)}
        handler.wfile.write(json.dumps(response).encode())


def handle_day_of_week_stats(handler):
    """GET /api/day-of-week-stats"""
    import server
    try:
        stats = server.db.get_day_of_week_stats(tenant_id=handler.tenant_id)
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(stats or {}).encode())
    except Exception as e:
        logger.exception("Error getting day stats")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())


def handle_retention_rates(handler):
    """GET /api/retention-rates"""
    import server
    try:
        rates = server.db.get_retention_rates(tenant_id=handler.tenant_id)
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps(rates or {}).encode())
    except Exception as e:
        logger.exception("Error getting retention rates")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
