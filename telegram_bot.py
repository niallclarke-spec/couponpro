"""
Telegram Bot Module

Handles Telegram webhook requests and generates promotional images.
Integrates with telegram_image_gen.py for image generation.
"""

import os
import json
import io
import re
import time
import requests
from telegram_image_gen import generate_promo_image

INDEX_CACHE = {
    'data': None,
    'expires_at': 0
}
CACHE_TTL = 300


def send_telegram_message(chat_id, text, bot_token):
    """
    Send a text message to a Telegram chat.
    
    Args:
        chat_id (int): Telegram chat ID
        text (str): Message text to send
        bot_token (str): Telegram bot token
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': text
        }
        response = requests.post(url, json=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False


def process_telegram_update(update_data):
    """
    Parse incoming webhook JSON from Telegram and extract command details.
    
    Args:
        update_data (dict): Raw webhook JSON from Telegram
        
    Returns:
        dict: Response dict with keys:
            - chat_id (int): Telegram chat ID
            - command (str): Template command name (normalized)
            - coupon_code (str): Coupon code from message
        None: If not a valid command
    """
    try:
        if not isinstance(update_data, dict):
            return None
        
        # Channels send 'channel_post' instead of 'message'
        message = update_data.get('message') or update_data.get('channel_post')
        if not message:
            return None
        
        text = message.get('text', '').strip()
        chat = message.get('chat', {})
        chat_id = chat.get('id')
        
        if not text or not chat_id:
            return None
        
        if not text.startswith('/'):
            return None
        
        text = text[1:]
        
        command = None
        coupon_code = None
        
        if '/' in text:
            parts = text.split('/', 1)
            command = parts[0].strip()
            coupon_code = parts[1].strip() if len(parts) > 1 else ''
        elif ' ' in text:
            parts = text.split(None, 1)
            command = parts[0].strip()
            coupon_code = parts[1].strip() if len(parts) > 1 else ''
        else:
            return None
        
        if not command or not coupon_code:
            return None
        
        command = command.lower()
        
        return {
            'chat_id': chat_id,
            'command': command,
            'coupon_code': coupon_code
        }
        
    except Exception as e:
        print(f"Error processing Telegram update: {e}")
        return None


def normalize_slug(slug):
    """
    Normalize slug by removing hyphens and underscores for comparison.
    
    Args:
        slug (str): Original slug
        
    Returns:
        str: Normalized slug (lowercase, no hyphens/underscores)
    """
    return re.sub(r'[-_]', '', slug.lower())


def find_template_by_command(command_name):
    """
    Find template matching command name by fetching index directly from Spaces.
    Uses in-memory cache with 5-minute TTL to reduce API calls and improve reliability.
    
    Matches command_name to directory slug, handling variations:
    - "blackfriday" matches "black-friday"
    - "flashsale" matches "flash-sale"
    - "15off2" matches "15-off-2"
    
    Args:
        command_name (str): Command name from message (e.g., "flashsale")
        
    Returns:
        dict: Template metadata with keys:
            - slug (str): Template slug
            - name (str): Template display name
            - square (str): Square variant image URL
            - story (str): Story variant image URL
        None: If template not found
        str: Error message starting with "ERROR:" if network issue
    """
    try:
        from object_storage import download_from_spaces
        
        current_time = time.time()
        if INDEX_CACHE['data'] is None or current_time > INDEX_CACHE['expires_at']:
            print(f"[TELEGRAM] Cache miss, downloading index.json")
            index_content = download_from_spaces('templates/index.json')
            if not index_content:
                return "ERROR:NETWORK"
            
            INDEX_CACHE['data'] = json.loads(index_content.decode('utf-8'))
            INDEX_CACHE['expires_at'] = current_time + CACHE_TTL
            print(f"[TELEGRAM] Index cached for {CACHE_TTL}s")
        else:
            print(f"[TELEGRAM] Cache hit, using cached index")
        
        data = INDEX_CACHE['data']
        normalized_command = normalize_slug(command_name)
        
        for template in data.get('templates', []):
            slug = template.get('slug', '')
            normalized_slug = normalize_slug(slug)
            
            if normalized_slug == normalized_command:
                return {
                    'slug': slug,
                    'name': template.get('name', ''),
                    'square': template.get('square', ''),
                    'story': template.get('story', '')
                }
        
        return None
        
    except Exception as e:
        print(f"[TELEGRAM] Error finding template: {e}")
        return "ERROR:EXCEPTION"


def generate_and_send_image(chat_id, template_slug, coupon_code, bot_token, variant='square'):
    """
    Generate promotional image and send to Telegram chat.
    
    Args:
        chat_id (int): Telegram chat ID
        template_slug (str): Template slug (e.g., "flash-sale")
        coupon_code (str): Coupon code to display
        bot_token (str): Telegram bot token
        variant (str): Image variant ('square' or 'story', default: 'square')
        
    Returns:
        dict: Response with keys:
            - success (bool): True if successful
            - message (str): Status message
    """
    try:
        # Validate coupon code before generating image
        try:
            import coupon_validator
            validation = coupon_validator.validate_coupon(coupon_code)
            
            if not validation['valid']:
                # Send error message to Telegram chat
                send_telegram_message(
                    chat_id, 
                    f"❌ Invalid coupon code '{coupon_code}'\n\n{validation['message']}", 
                    bot_token
                )
                return {
                    'success': False,
                    'message': f'Invalid coupon: {validation["message"]}'
                }
        except Exception as val_error:
            print(f"[TELEGRAM] Coupon validation error: {val_error}")
            send_telegram_message(
                chat_id,
                f"⚠️ Unable to validate coupon '{coupon_code}'. Please try again later.",
                bot_token
            )
            return {
                'success': False,
                'message': f'Validation error: {str(val_error)}'
            }
        
        from object_storage import download_from_spaces
        
        meta_content = download_from_spaces(f'templates/{template_slug}/meta.json')
        if not meta_content:
            return {
                'success': False,
                'message': 'Template metadata not found'
            }
        
        metadata = json.loads(meta_content.decode('utf-8'))
        
        # Smart fallback: prefer square, then story, then fail
        if variant not in metadata:
            if 'square' in metadata:
                variant = 'square'
            elif 'story' in metadata:
                variant = 'story'
            else:
                return {
                    'success': False,
                    'message': 'Template has no available variants'
                }
        
        variant_data = metadata.get(variant, {})
        
        image_url = variant_data.get('imageUrl')
        box = variant_data.get('box')
        max_font_px = variant_data.get('maxFontPx')
        font_color = variant_data.get('fontColor')
        
        if not image_url:
            return {
                'success': False,
                'message': 'Template image URL not found'
            }
        
        image = generate_promo_image(
            template_image_url=image_url,
            coupon_code=coupon_code,
            box=box,
            max_font_px=max_font_px,
            font_color=font_color,
            logo_url=None,
            variant=variant
        )
        
        bio = io.BytesIO()
        image.save(bio, format='PNG')
        bio.seek(0)
        
        url = f'https://api.telegram.org/bot{bot_token}/sendPhoto'
        files = {'photo': ('promo.png', bio, 'image/png')}
        data = {'chat_id': chat_id}
        
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            return {
                'success': True,
                'message': 'Image sent successfully'
            }
        else:
            return {
                'success': False,
                'message': f'Failed to send image: {response.text}'
            }
        
    except Exception as e:
        print(f"Error generating/sending image: {e}")
        return {
            'success': False,
            'message': f'Failed to generate image: {str(e)}'
        }


def handle_telegram_webhook(request_body, bot_token):
    """
    Main handler for Telegram webhook requests.
    
    Orchestrates the flow: parse → find template → generate → send → log
    
    Args:
        request_body (dict): Webhook request body from Telegram
        bot_token (str): Telegram bot token
        
    Returns:
        dict: Response with keys:
            - success (bool): True if successful
            - message (str): Status or error message
    """
    chat_id = None
    template_slug = None
    coupon_code = None
    success = False
    error_type = None
    
    try:
        parsed = process_telegram_update(request_body)
        
        if not parsed:
            return {
                'success': False,
                'message': 'Invalid command format'
            }
        
        chat_id = parsed['chat_id']
        command = parsed['command']
        coupon_code = parsed['coupon_code']
        
        template = find_template_by_command(command)
        
        if isinstance(template, str) and template.startswith('ERROR:'):
            error_type = 'network'
            error_message = '⚠️ Connection issue. Please try again in a moment.'
            url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': error_message
            }
            requests.post(url, json=data)
            _log_usage(chat_id, template_slug, coupon_code, success, error_type)
            return {
                'success': False,
                'message': f'Network error: {template}'
            }
        
        if not template:
            error_type = 'template_not_found'
            url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': f'❌ Template "{command}" not found. Check available templates in the channel.'
            }
            requests.post(url, json=data)
            _log_usage(chat_id, template_slug, coupon_code, success, error_type)
            return {
                'success': False,
                'message': 'Template not found'
            }
        
        template_slug = template['slug']
        
        result = generate_and_send_image(
            chat_id=chat_id,
            template_slug=template_slug,
            coupon_code=coupon_code,
            bot_token=bot_token,
            variant='square'
        )
        
        success = result['success']
        
        if not success:
            if 'Invalid coupon' in result.get('message', ''):
                error_type = 'invalid_coupon'
            elif 'Validation error' in result.get('message', ''):
                error_type = 'validation_error'
            else:
                error_type = 'generation_failed'
            
            url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': 'Failed to generate image'
            }
            requests.post(url, json=data)
        
        _log_usage(chat_id, template_slug, coupon_code, success, error_type)
        return result
        
    except Exception as e:
        error_type = 'exception'
        print(f"Error handling webhook: {e}")
        _log_usage(chat_id, template_slug, coupon_code, success, error_type)
        return {
            'success': False,
            'message': f'Error: {str(e)}'
        }


def _log_usage(chat_id, template_slug, coupon_code, success, error_type):
    """
    Internal helper to log bot usage. Silently fails to avoid disrupting bot.
    """
    try:
        import db
        if chat_id:
            db.log_bot_usage(chat_id, template_slug, coupon_code, success, error_type)
    except Exception as e:
        print(f"[BOT_USAGE] Logging failed (non-critical): {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("Telegram Bot Module")
    print("=" * 60)
    print("\nHandles Telegram webhook requests and generates promo images.")
    print("\n" + "=" * 60)
    print("EXAMPLE USAGE:")
    print("=" * 60)
    print()
    print("from telegram_bot import handle_telegram_webhook")
    print()
    print("# Webhook request body from Telegram")
    print("request_body = {")
    print('    "update_id": 123456,')
    print('    "message": {')
    print('        "message_id": 1,')
    print('        "chat": {"id": 987654321},')
    print('        "text": "/flash-sale/SAVE50"')
    print('    }')
    print("}")
    print()
    print("# Handle webhook")
    print("result = handle_telegram_webhook(")
    print("    request_body=request_body,")
    print("    bot_token='YOUR_BOT_TOKEN'")
    print(")")
    print()
    print("# Supported command formats:")
    print("# - /flash-sale/CODE")
    print("# - /flashsale/CODE")
    print("# - /flash-sale CODE")
    print("# - /flashsale CODE")
    print()
    print("=" * 60)
