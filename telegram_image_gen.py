"""
Telegram Image Generation Module

Ports canvas rendering logic from index.html to Python/Pillow.
Generates promotional images with auto-fitted text and optional logo overlay.
"""

import re
import os
import io
from urllib.parse import urlparse
from urllib.request import urlopen
from PIL import Image, ImageDraw, ImageFont


def sanitize_coupon_code(code):
    """
    Sanitize coupon code: uppercase, spaces to dashes, only A-Z 0-9 - _
    
    Args:
        code (str): Raw coupon code
        
    Returns:
        str: Sanitized coupon code
    """
    if not code:
        return ''
    # Uppercase and replace spaces with dashes
    code = code.upper().replace(' ', '-')
    # Remove any character that's not A-Z, 0-9, dash, or underscore
    code = re.sub(r'[^A-Z0-9\-_]', '', code)
    return code


def load_image_from_url_or_path(url_or_path):
    """
    Load image from URL or local file path.
    Supports PNG, JPEG, and other Pillow-compatible formats.
    Note: SVG files are not natively supported by Pillow. Use PNG logos instead.
    
    Args:
        url_or_path (str): URL (http/https) or local file path
        
    Returns:
        PIL.Image: Loaded image
        
    Raises:
        ValueError: If SVG file is provided (not supported)
    """
    # Check if it's an SVG file
    if url_or_path.lower().endswith('.svg'):
        raise ValueError(
            f"SVG files are not supported. Please use PNG format instead. "
            f"Try replacing '{url_or_path}' with a PNG version."
        )
    
    parsed = urlparse(url_or_path)
    
    if parsed.scheme in ('http', 'https'):
        # Download from URL
        with urlopen(url_or_path) as response:
            image_data = response.read()
        return Image.open(io.BytesIO(image_data))
    else:
        # Load from local path
        return Image.open(url_or_path)


def get_font(size, bold=True):
    """
    Get font with specified size and weight.
    Tries to find system fonts, falls back to default.
    
    Args:
        size (int): Font size in pixels
        bold (bool): Whether to use bold weight
        
    Returns:
        ImageFont: Font object
    """
    font_names = [
        'Arial Bold',
        'Arial-Bold',
        'ArialBold',
        'Helvetica Bold',
        'Helvetica-Bold',
        'DejaVuSans-Bold',
        'FreeSansBold',
    ] if bold else [
        'Arial',
        'Helvetica',
        'DejaVuSans',
        'FreeSans',
    ]
    
    # Try to load system fonts
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except (OSError, IOError):
            pass
    
    # Try common font paths on Linux
    common_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
    ] if bold else [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                pass
    
    # Fall back to default font
    return ImageFont.load_default()


def compute_auto_font_px(draw, text, max_width_px, max_px, min_px=8):
    """
    Binary search to find largest font size that fits within max_width_px.
    
    Port of computeAutoFontPx from index.html (lines 315-326).
    
    Args:
        draw (ImageDraw.Draw): Draw object for text measurement
        text (str): Text to measure
        max_width_px (float): Maximum width in pixels
        max_px (float): Maximum font size
        min_px (int): Minimum font size (default: 8)
        
    Returns:
        int: Optimal font size in pixels
    """
    min_val = max(8, int(min_px or 8))
    lo = min_val
    hi = max(min_val, int(max_px or min_val))
    
    if not max_width_px or max_width_px <= 0:
        return min_val
    
    # Binary search for optimal font size
    while hi - lo > 0.5:
        mid = (hi + lo) / 2
        font = get_font(int(mid), bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        
        if width <= max_width_px:
            lo = mid
        else:
            hi = mid
    
    return int(lo)


def draw_text_auto_fit(draw, text, nat_w, nat_h, box, max_font_px, font_color=None):
    """
    Draw text with auto-fit sizing and alignment based on box parameters.
    
    Port of drawTextAutoFit from index.html (lines 328-352).
    Updated to use bbox-based vertical centering for accurate positioning.
    
    Args:
        draw (ImageDraw.Draw): Draw object
        text (str): Text to draw
        nat_w (int): Natural width of image
        nat_h (int): Natural height of image
        box (dict): Box parameters with keys:
            - leftPct: Left position as percentage (default: 5)
            - topPct: Top position as percentage (default: 80)
            - widthPct: Width as percentage (default: 90)
            - heightPct: Height as percentage (default: 12)
            - hAlign: Horizontal alignment ('left', 'center', 'right', default: 'center')
            - vAlign: Vertical alignment ('top', 'middle', 'bottom', default: 'bottom')
        max_font_px (int): Maximum font size
        font_color (str): Font color (default: '#ffffff')
    """
    if not box:
        box = {}
    
    # Calculate box dimensions
    left = round(nat_w * (box.get('leftPct', 5) / 100))
    top = round(nat_h * (box.get('topPct', 80) / 100))
    width = round(nat_w * (box.get('widthPct', 90) / 100))
    height = round(nat_h * (box.get('heightPct', 12) / 100))
    
    # Determine font size cap
    cap = min(max_font_px, height)
    px = compute_auto_font_px(draw, text, width, cap, 8)
    
    # Get font
    font = get_font(px, bold=True)
    
    # Get actual text bounding box for precise positioning
    stroke_width = max(2, int(px * 0.08))
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate horizontal alignment
    h_align = box.get('hAlign', 'center')
    if h_align == 'center':
        x = left + round(width / 2) - round(text_width / 2)
    elif h_align == 'right':
        x = left + width - text_width
    else:  # left
        x = left
    
    # Calculate vertical alignment using bbox height
    v_align = box.get('vAlign', 'bottom')
    if v_align == 'middle':
        # Center text vertically in the box
        y = top + round(height / 2) - round(text_height / 2)
    elif v_align == 'bottom':
        # Align text to bottom of box
        y = top + height - text_height
    else:  # top
        # Align text to top of box
        y = top
    
    # Adjust for bbox offset (bbox top is negative for most fonts)
    y = y - bbox[1]
    
    # Draw text with stroke (outline)
    # Use 'la' anchor (left-alphabetic) since we've already calculated exact position
    fill_color = font_color or '#ffffff'
    
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill_color,
        anchor='la',
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0)  # Black outline
    )


def generate_promo_image(
    template_image_url,
    coupon_code,
    box=None,
    max_font_px=None,
    font_color=None,
    logo_url=None,
    variant='square'
):
    """
    Generate promotional image with coupon code and optional logo.
    
    Main function that combines template loading, text rendering, and logo overlay.
    
    Args:
        template_image_url (str): URL or path to template image
        coupon_code (str): Coupon code to display (will be sanitized)
        box (dict, optional): Text box parameters (leftPct, topPct, widthPct, heightPct, hAlign, vAlign)
        max_font_px (int, optional): Maximum font size (default: image height * 0.12)
        font_color (str, optional): Font color (default: '#ffffff')
        logo_url (str, optional): URL or path to logo image
        variant (str): Variant type for default box sizing ('square' or 'story')
        
    Returns:
        PIL.Image: Generated promotional image
    """
    # Load template image
    template = load_image_from_url_or_path(template_image_url)
    template = template.convert('RGBA')
    
    # Get natural dimensions
    nat_w, nat_h = template.size
    
    # Sanitize coupon code
    sanitized_code = sanitize_coupon_code(coupon_code)
    
    # Set default box if not provided
    if box is None:
        box = {
            'leftPct': 5,
            'topPct': 78,
            'widthPct': 90,
            'heightPct': 12,
            'hAlign': 'center',
            'vAlign': 'bottom'
        }
    
    # Set default max font size if not provided
    if max_font_px is None:
        max_font_px = float('inf')
    
    # Create drawing context
    draw = ImageDraw.Draw(template)
    
    # Draw text
    draw_text_auto_fit(draw, sanitized_code, nat_w, nat_h, box, max_font_px, font_color)
    
    # Add logo if provided
    if logo_url:
        try:
            logo = load_image_from_url_or_path(logo_url)
            logo = logo.convert('RGBA')
            
            # Calculate logo dimensions (same as frontend)
            nat_min = min(nat_w, nat_h)
            margin = max(20, round(nat_min * 0.04))
            diameter = max(32, round(nat_min * 0.12))
            radius = diameter // 2
            
            # Position in top-left corner
            x = margin
            y = margin
            
            # Create circular mask
            mask = Image.new('L', (diameter, diameter), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, diameter, diameter), fill=255)
            
            # Resize logo to fit circle (crop to square first)
            logo_w, logo_h = logo.size
            side = min(logo_w, logo_h)
            sx = (logo_w - side) // 2
            sy = (logo_h - side) // 2
            logo_cropped = logo.crop((sx, sy, sx + side, sy + side))
            logo_resized = logo_cropped.resize((diameter, diameter), Image.Resampling.LANCZOS)
            
            # Paste logo with circular mask
            template.paste(logo_resized, (x, y), mask)
            
        except Exception as e:
            print(f"Warning: Failed to load/apply logo: {e}")
    
    return template


if __name__ == '__main__':
    # Example usage
    print("=" * 60)
    print("Telegram Image Generation Module")
    print("=" * 60)
    print("\nThis module ports canvas rendering logic from index.html to")
    print("Python/Pillow for generating promotional images.")
    print("\n" + "=" * 60)
    print("EXAMPLE USAGE:")
    print("=" * 60)
    print()
    print("from telegram_image_gen import generate_promo_image")
    print()
    print("# Basic usage")
    print("img = generate_promo_image(")
    print("    template_image_url='assets/templates/15-off-2/square.png',")
    print("    coupon_code='WELCOME 30'")
    print(")")
    print("img.save('output.png')")
    print()
    print("# With logo and custom settings")
    print("img = generate_promo_image(")
    print("    template_image_url='assets/templates/flash-sale/story.png',")
    print("    coupon_code='FLASH-SALE-50',")
    print("    box={")
    print("        'leftPct': 5,")
    print("        'topPct': 75,")
    print("        'widthPct': 90,")
    print("        'heightPct': 15,")
    print("        'hAlign': 'center',")
    print("        'vAlign': 'bottom'")
    print("    },")
    print("    max_font_px=120,")
    print("    font_color='#ffffff',")
    print("    logo_url='assets/fp-site-logo.png'")
    print(")")
    print("img.save('promo.png')")
    print()
    print("# From URL (Digital Ocean Spaces, etc.)")
    print("img = generate_promo_image(")
    print("    template_image_url='https://example.com/template.png',")
    print("    coupon_code='SAVE30',")
    print("    logo_url='https://example.com/logo.png'")
    print(")")
    print()
    print("=" * 60)
    print("NOTE: Use PNG logos. SVG files are not supported.")
    print("=" * 60)
