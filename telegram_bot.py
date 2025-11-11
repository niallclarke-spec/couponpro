"""
Telegram Bot Module - Conversational Bot

Handles Telegram bot interactions with guided conversation flow.
Users are prompted for coupon code, then select templates via inline buttons.
"""

import os
import json
import io
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram_image_gen import generate_promo_image
import coupon_validator

# Conversation states
WAITING_FOR_COUPON = 1

# Index cache for template data
INDEX_CACHE = {
    'data': None,
    'expires_at': 0
}
CACHE_TTL = 300


def get_templates():
    """
    Fetch templates from index.json (cached).
    
    Returns:
        list: List of template dicts with keys: slug, name, square, story
        None: If error fetching templates
    """
    try:
        from object_storage import download_from_spaces
        
        current_time = time.time()
        if INDEX_CACHE['data'] is None or current_time > INDEX_CACHE['expires_at']:
            print(f"[TELEGRAM] Cache miss, downloading index.json")
            index_content = download_from_spaces('templates/index.json')
            if not index_content:
                return None
            
            INDEX_CACHE['data'] = json.loads(index_content.decode('utf-8'))
            INDEX_CACHE['expires_at'] = current_time + CACHE_TTL
            print(f"[TELEGRAM] Index cached for {CACHE_TTL}s")
        else:
            print(f"[TELEGRAM] Cache hit, using cached index")
        
        return INDEX_CACHE['data'].get('templates', [])
        
    except Exception as e:
        print(f"[TELEGRAM] Error fetching templates: {e}")
        return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /start command - initiate conversation.
    
    Returns:
        int: Next conversation state (WAITING_FOR_COUPON)
    """
    welcome_message = (
        "👋 Welcome to PromoStack!\n\n"
        "I'll help you create professional promotional images with your FunderPro coupon codes.\n\n"
        "Please enter your FunderPro coupon code to get started:"
    )
    await update.message.reply_text(welcome_message)
    return WAITING_FOR_COUPON


async def handle_coupon_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle coupon code input - validate and show template selection.
    
    Returns:
        int: Next state (WAITING_FOR_COUPON if invalid, ConversationHandler.END if valid)
    """
    coupon_code = update.message.text.strip().upper()
    chat_id = update.effective_chat.id
    
    # Validate coupon
    try:
        validation = coupon_validator.validate_coupon(coupon_code)
        
        if not validation['valid']:
            # Invalid coupon - ask to try again
            await update.message.reply_text(
                f"❌ Sorry, {coupon_code} doesn't appear to be a valid FunderPro coupon. Please check and try again."
            )
            # Log failed validation
            _log_usage(chat_id, None, coupon_code, False, 'invalid_coupon')
            return WAITING_FOR_COUPON
        
    except Exception as val_error:
        print(f"[TELEGRAM] Coupon validation error: {val_error}")
        await update.message.reply_text(
            f"⚠️ Unable to validate coupon. Please try again later."
        )
        _log_usage(chat_id, None, coupon_code, False, 'validation_error')
        return WAITING_FOR_COUPON
    
    # Coupon is valid - store in context and show template selection
    context.user_data['coupon_code'] = coupon_code
    
    # Get templates
    templates = get_templates()
    if not templates:
        await update.message.reply_text(
            "⚠️ Unable to load templates. Please try again later."
        )
        _log_usage(chat_id, None, coupon_code, False, 'templates_error')
        return ConversationHandler.END
    
    # Build inline keyboard with template buttons
    keyboard = []
    for template in templates:
        button = InlineKeyboardButton(
            template.get('name', template.get('slug', 'Template')),
            callback_data=f"template:{template.get('slug')}"
        )
        keyboard.append([button])
    
    # Add "Generate All" button
    keyboard.append([InlineKeyboardButton("🎨 Generate All Templates", callback_data="template:all")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Coupon {coupon_code} is valid!\n\nSelect a template to generate:",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END


async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle template button click - generate and send image.
    """
    query = update.callback_query
    await query.answer()
    
    coupon_code = context.user_data.get('coupon_code')
    if not coupon_code:
        await query.message.reply_text("Please start over with /start")
        return
    
    # Parse callback data
    callback_data = query.data
    if not callback_data.startswith('template:'):
        return
    
    template_selection = callback_data.replace('template:', '')
    chat_id = update.effective_chat.id
    
    # Handle "Generate All"
    if template_selection == 'all':
        templates = get_templates()
        if not templates:
            await query.message.reply_text("⚠️ Unable to load templates.")
            return
        
        await query.message.reply_text(f"🎨 Generating all templates with coupon {coupon_code}...")
        
        for template in templates:
            template_slug = template.get('slug')
            await _generate_and_send(query.message, chat_id, template_slug, coupon_code)
        
        await query.message.reply_text(
            "✅ All templates generated!\n\n"
            "💡 *What's next?*\n"
            "• /generate - Generate templates again\n"
            "• /start - Use a different coupon code\n"
            "• /help - View all commands",
            parse_mode='Markdown'
        )
        return
    
    # Handle single template selection
    template_slug = template_selection
    await query.message.reply_text(f"🎨 Generating {template_slug} with coupon {coupon_code}...")
    await _generate_and_send(query.message, chat_id, template_slug, coupon_code)


async def _generate_and_send(message, chat_id, template_slug, coupon_code):
    """
    Internal helper to generate and send a template image.
    """
    try:
        from object_storage import download_from_spaces
        
        # Download template metadata
        meta_content = download_from_spaces(f'templates/{template_slug}/meta.json')
        if not meta_content:
            await message.reply_text(f"❌ Template {template_slug} not found.")
            _log_usage(chat_id, template_slug, coupon_code, False, 'template_not_found')
            return
        
        metadata = json.loads(meta_content.decode('utf-8'))
        
        # Smart fallback: prefer square, then story
        variant = 'square'
        if 'square' not in metadata:
            if 'story' in metadata:
                variant = 'story'
            else:
                await message.reply_text(f"❌ Template {template_slug} has no available variants.")
                _log_usage(chat_id, template_slug, coupon_code, False, 'no_variants')
                return
        
        variant_data = metadata.get(variant, {})
        
        image_url = variant_data.get('imageUrl')
        box = variant_data.get('box')
        max_font_px = variant_data.get('maxFontPx')
        font_color = variant_data.get('fontColor')
        
        if not image_url:
            await message.reply_text(f"❌ Template image URL not found.")
            _log_usage(chat_id, template_slug, coupon_code, False, 'image_url_missing')
            return
        
        # Generate image
        image = generate_promo_image(
            template_image_url=image_url,
            coupon_code=coupon_code,
            box=box,
            max_font_px=max_font_px,
            font_color=font_color,
            logo_url=None,
            variant=variant
        )
        
        # Send to Telegram
        bio = io.BytesIO()
        image.save(bio, format='PNG')
        bio.seek(0)
        
        await message.reply_photo(photo=bio, filename=f'{template_slug}-{coupon_code}.png')
        _log_usage(chat_id, template_slug, coupon_code, True, None)
        
        # Show helpful next steps
        await message.reply_text(
            "✅ Image generated!\n\n"
            "💡 *What's next?*\n"
            "• /generate - Create more images with the same coupon\n"
            "• /start - Use a different coupon code\n"
            "• /help - View all commands",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        print(f"[TELEGRAM] Error generating image: {e}")
        await message.reply_text(f"❌ Failed to generate image. Please try again.")
        _log_usage(chat_id, template_slug, coupon_code, False, 'generation_failed')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show instructions."""
    help_text = (
        "📖 *How to Use PromoStack Bot*\n\n"
        "*Available Commands:*\n"
        "/start - Enter a new coupon code and generate images\n"
        "/generate - Generate templates with your current coupon\n"
        "/help - Show this help message\n\n"
        "*How It Works:*\n"
        "1️⃣ Send /start and enter your FunderPro coupon code\n"
        "2️⃣ Choose a template from the menu\n"
        "3️⃣ Receive your promotional image!\n\n"
        "💡 *Tip:* Use /start anytime to enter a different coupon code"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate command - regenerate templates with stored coupon."""
    coupon_code = context.user_data.get('coupon_code')
    
    if not coupon_code:
        await update.message.reply_text(
            "⚠️ No coupon code found. Please use /start to enter your coupon code first."
        )
        return
    
    # Get templates and show selection
    templates = get_templates()
    if not templates:
        await update.message.reply_text("⚠️ Unable to load templates. Please try again later.")
        return
    
    # Build inline keyboard with template buttons
    keyboard = []
    for template in templates:
        button = InlineKeyboardButton(
            template.get('name', template.get('slug', 'Template')),
            callback_data=f"template:{template.get('slug')}"
        )
        keyboard.append([button])
    
    # Add "Generate All" button
    keyboard.append([InlineKeyboardButton("🎨 Generate All Templates", callback_data="template:all")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Select a template to generate with coupon *{coupon_code}*:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command - exit conversation."""
    await update.message.reply_text("Conversation cancelled. Use /start to begin again.")
    return ConversationHandler.END


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


async def post_init(application: Application):
    """
    Set up bot commands menu after initialization.
    """
    commands = [
        BotCommand("start", "Enter a new coupon code and generate images"),
        BotCommand("generate", "Generate templates with your current coupon"),
        BotCommand("help", "Show help and instructions")
    ]
    await application.bot.set_my_commands(commands)
    print("[TELEGRAM] Bot commands menu configured")


def create_bot_application(bot_token):
    """
    Create and configure the Telegram bot application.
    
    Args:
        bot_token (str): Telegram bot token
        
    Returns:
        Application: Configured bot application
    """
    # Create application
    application = Application.builder().token(bot_token).post_init(post_init).build()
    
    # Define conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            WAITING_FOR_COUPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coupon_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
        allow_reentry=True
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('generate', generate_command))
    application.add_handler(CallbackQueryHandler(handle_template_selection))
    
    return application


def run_bot(bot_token):
    """
    Start the Telegram bot with polling.
    
    Args:
        bot_token (str): Telegram bot token
    """
    print(f"[TELEGRAM] Starting bot...")
    application = create_bot_application(bot_token)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    # Use test bot token for development
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN_TEST') or os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("ERROR: No bot token found. Set TELEGRAM_BOT_TOKEN_TEST or TELEGRAM_BOT_TOKEN")
    else:
        print("=" * 60)
        print("PromoStack Conversational Telegram Bot")
        print("=" * 60)
        print(f"\nBot token: {'TEST' if os.getenv('TELEGRAM_BOT_TOKEN_TEST') else 'PRODUCTION'}")
        print("\nConversational flow:")
        print("1. User: /start")
        print("2. Bot: Please enter your FunderPro coupon code")
        print("3. User: WELCOME30")
        print("4. Bot: ✅ Coupon valid! [Shows template buttons]")
        print("5. User: Clicks template button")
        print("6. Bot: Generates and sends image")
        print("\n" + "=" * 60)
        run_bot(bot_token)
