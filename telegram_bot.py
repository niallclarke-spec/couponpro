"""
Telegram Bot Module

Handles Telegram webhook requests and generates promotional images.
Integrates with telegram_image_gen.py for image generation.
"""

import os
import json
import io
import re
import requests
from telegram import Update
from telegram_image_gen import generate_promo_image


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
        
        message = update_data.get('message')
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
    Find template matching command name by scanning assets/templates/ directory.
    
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
    """
    try:
        index_path = 'assets/templates/index.json'
        
        if not os.path.exists(index_path):
            return None
        
        with open(index_path, 'r') as f:
            data = json.load(f)
        
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
        print(f"Error finding template: {e}")
        return None


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
        meta_path = f'assets/templates/{template_slug}/meta.json'
        
        if not os.path.exists(meta_path):
            return {
                'success': False,
                'message': 'Template metadata not found'
            }
        
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        
        if variant not in metadata:
            variant = 'square'
        
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
    
    Orchestrates the flow: parse → find template → generate → send
    
    Args:
        request_body (dict): Webhook request body from Telegram
        bot_token (str): Telegram bot token
        
    Returns:
        dict: Response with keys:
            - success (bool): True if successful
            - message (str): Status or error message
    """
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
        
        if not template:
            url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': 'Template not found'
            }
            requests.post(url, json=data)
            return {
                'success': False,
                'message': 'Template not found'
            }
        
        result = generate_and_send_image(
            chat_id=chat_id,
            template_slug=template['slug'],
            coupon_code=coupon_code,
            bot_token=bot_token,
            variant='square'
        )
        
        if not result['success']:
            url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': 'Failed to generate image'
            }
            requests.post(url, json=data)
        
        return result
        
    except Exception as e:
        print(f"Error handling webhook: {e}")
        return {
            'success': False,
            'message': f'Error: {str(e)}'
        }


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
