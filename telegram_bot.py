"""
Telegram Bot Module - Conversational Bot

Handles Telegram bot interactions with guided conversation flow.
Users are prompted for coupon code, then select templates via inline buttons.
"""

import os
import json
import io
import time
import asyncio
import threading
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
from telegram.error import Forbidden, RetryAfter, TelegramError
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
        "👋 Welcome to FunderPro Affiliate Hub!\n\n"
        "Here you can find all the latest promos available. Generate promo images "
        "with your unique coupon code in seconds.\n\n"
        "👉 Please enter your FunderPro coupon code to get started:"
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
    
    # Validate coupon (run in thread to avoid blocking event loop)
    import asyncio
    
    try:
        validation = await asyncio.to_thread(coupon_validator.validate_coupon, coupon_code)
        
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
    
    # Coupon is valid - store in context and track user
    context.user_data['coupon_code'] = coupon_code
    
    # Track user for broadcast capability
    try:
        import db
        db.track_bot_user(chat_id, coupon_code)
    except Exception as track_error:
        print(f"[TELEGRAM] Failed to track user (non-critical): {track_error}")
    
    # Get templates (run in thread to avoid blocking event loop)
    try:
        templates = await asyncio.to_thread(get_templates)
    except Exception as template_error:
        print(f"[TELEGRAM] Template loading error: {template_error}")
        templates = None
    
    if not templates:
        await update.message.reply_text(
            "⚠️ Unable to load templates. Please try again later."
        )
        _log_usage(chat_id, None, coupon_code, False, 'templates_error')
        return ConversationHandler.END
    
    # Send each template with preview image and button
    for template in templates:
        template_name = template.get('name', template.get('slug', 'Template'))
        template_slug = template.get('slug')
        preview_url = template.get('square') or template.get('story')
        
        # Create button for this template
        keyboard = [[InlineKeyboardButton(
            f"✨ Generate {template_name}",
            callback_data=f"template:{template_slug}"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if preview_url:
            # Send with preview image
            try:
                await update.message.reply_photo(
                    photo=preview_url,
                    caption=f"📸 *{template_name}*",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"[TELEGRAM] Failed to send preview for {template_slug}: {e}")
                # Fallback to text-only if preview fails
                await update.message.reply_text(
                    f"📸 *{template_name}*",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            # No preview available - send text-only button
            await update.message.reply_text(
                f"📸 *{template_name}*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # Add "Generate All" button in separate message
    keyboard = [[InlineKeyboardButton("🎨 Generate All Templates", callback_data="template:all")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Coupon *{coupon_code}* is valid!\n\nOr generate all at once:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END


async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle template button click - generate and send image.
    """
    query = update.callback_query
    await query.answer()
    
    print(f"[TELEGRAM] Template button clicked: {query.data}")
    
    coupon_code = context.user_data.get('coupon_code')
    if not coupon_code:
        print(f"[TELEGRAM] No coupon code found in user_data")
        await query.message.reply_text("Please start over with /start")
        return
    
    print(f"[TELEGRAM] Coupon code: {coupon_code}")
    
    # Parse callback data
    callback_data = query.data
    if not callback_data.startswith('template:'):
        return
    
    template_selection = callback_data.replace('template:', '')
    chat_id = update.effective_chat.id
    
    # Handle "Generate All"
    if template_selection == 'all':
        import asyncio
        try:
            templates = await asyncio.to_thread(get_templates)
        except Exception:
            templates = None
        
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
    print(f"[TELEGRAM] Generating single template: {template_slug}")
    await query.message.reply_text(f"🎨 Generating {template_slug} with coupon {coupon_code}...")
    await _generate_and_send(query.message, chat_id, template_slug, coupon_code)
    print(f"[TELEGRAM] Generation complete for {template_slug}")


def _generate_image_sync(template_slug, coupon_code):
    """
    Synchronous helper to perform blocking image generation.
    Returns: (image_bio, error_message) tuple
    """
    from object_storage import download_from_spaces
    
    try:
        # Download template metadata
        meta_content = download_from_spaces(f'templates/{template_slug}/meta.json')
        if not meta_content:
            return None, 'template_not_found'
        
        metadata = json.loads(meta_content.decode('utf-8'))
        
        # Smart fallback: prefer square, then story
        variant = 'square'
        if 'square' not in metadata:
            if 'story' in metadata:
                variant = 'story'
            else:
                return None, 'no_variants'
        
        variant_data = metadata.get(variant, {})
        
        image_url = variant_data.get('imageUrl')
        box = variant_data.get('box')
        max_font_px = variant_data.get('maxFontPx')
        font_color = variant_data.get('fontColor')
        
        if not image_url:
            return None, 'image_url_missing'
        
        # Generate image (blocking operation)
        image = generate_promo_image(
            template_image_url=image_url,
            coupon_code=coupon_code,
            box=box,
            max_font_px=max_font_px,
            font_color=font_color,
            logo_url=None,
            variant=variant
        )
        
        # Convert to BytesIO
        bio = io.BytesIO()
        image.save(bio, format='PNG')
        bio.seek(0)
        
        return bio, None
        
    except Exception as e:
        print(f"[TELEGRAM] Image generation error: {e}")
        return None, 'generation_failed'


async def _generate_and_send(message, chat_id, template_slug, coupon_code):
    """
    Internal helper to generate and send a template image.
    Runs blocking I/O in thread to keep event loop responsive.
    """
    import asyncio
    
    print(f"[TELEGRAM] _generate_and_send called: template={template_slug}, coupon={coupon_code}")
    
    try:
        # Run blocking image generation in thread
        print(f"[TELEGRAM] Starting image generation...")
        image_bio, error = await asyncio.to_thread(_generate_image_sync, template_slug, coupon_code)
        print(f"[TELEGRAM] Image generation finished: error={error}")
        
        if error:
            error_messages = {
                'template_not_found': f"❌ Template {template_slug} not found.",
                'no_variants': f"❌ Template {template_slug} has no available variants.",
                'image_url_missing': f"❌ Template image URL not found.",
                'generation_failed': f"❌ Failed to generate image. Please try again."
            }
            await message.reply_text(error_messages.get(error, "❌ An error occurred."))
            _log_usage(chat_id, template_slug, coupon_code, False, error)
            return
        
        # Send to Telegram
        await message.reply_photo(photo=image_bio, filename=f'{template_slug}-{coupon_code}.png')
        _log_usage(chat_id, template_slug, coupon_code, True, None)
        
        # Send personalized FunderPro challenge link
        challenge_url = f"https://prop.funderpro.com/buy-challenge/?promo={coupon_code}"
        await message.reply_text(
            f"✅ *Image generated!*\n\n"
            f"🔗 *Your Personal Referral Link:*\n"
            f"{challenge_url}\n\n"
            f"⚡ Give your audience one-click access to your offer with this instant checkout link.\n\n"
            f"*What's next?*\n"
            f"• /generate - Create more images with the same coupon\n"
            f"• /start - Use a different coupon code\n"
            f"• /help - View all commands",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        print(f"[TELEGRAM] Error in _generate_and_send: {e}")
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
    
    # Get templates and show selection (run in thread to avoid blocking)
    import asyncio
    try:
        templates = await asyncio.to_thread(get_templates)
    except Exception:
        templates = None
    
    if not templates:
        await update.message.reply_text("⚠️ Unable to load templates. Please try again later.")
        return
    
    # Send each template with preview image and button
    for template in templates:
        template_name = template.get('name', template.get('slug', 'Template'))
        template_slug = template.get('slug')
        preview_url = template.get('square') or template.get('story')
        
        # Create button for this template
        keyboard = [[InlineKeyboardButton(
            f"✨ Generate {template_name}",
            callback_data=f"template:{template_slug}"
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if preview_url:
            # Send with preview image
            try:
                await update.message.reply_photo(
                    photo=preview_url,
                    caption=f"📸 *{template_name}*",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                print(f"[TELEGRAM] Failed to send preview for {template_slug}: {e}")
                # Fallback to text-only if preview fails
                await update.message.reply_text(
                    f"📸 *{template_name}*",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            # No preview available - send text-only button
            await update.message.reply_text(
                f"📸 *{template_name}*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # Add "Generate All" button in separate message
    keyboard = [[InlineKeyboardButton("🎨 Generate All Templates", callback_data="template:all")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Generate all templates with coupon *{coupon_code}*:",
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


async def _send_broadcast_messages(job_id, users, message, bot_token):
    """
    Async function to send broadcast messages with rate limiting.
    
    Args:
        job_id (int): Broadcast job ID
        users (list): List of user dicts with chat_id
        message (str): Message to send
        bot_token (str): Bot token to use for sending
    """
    import db
    
    # Create a temporary bot application for sending
    from telegram import Bot
    bot = Bot(token=bot_token)
    
    sent_count = 0
    failed_count = 0
    
    # Update job status to processing
    db.update_broadcast_job(job_id, status='processing')
    
    # Rate limiting: 20 messages per second (safe buffer below Telegram's 30/s limit)
    rate_limit_delay = 0.05  # 50ms between messages = 20 messages/second
    
    for user in users:
        chat_id = user['chat_id']
        
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )
            sent_count += 1
            print(f"[BROADCAST] Sent to {chat_id} ({sent_count}/{len(users)})")
            
            # Update progress every 10 messages
            if sent_count % 10 == 0:
                db.update_broadcast_job(job_id, sent_count=sent_count, failed_count=failed_count)
            
            # Rate limit
            await asyncio.sleep(rate_limit_delay)
            
        except Forbidden:
            # User blocked the bot - remove them
            print(f"[BROADCAST] User {chat_id} blocked bot, removing")
            db.remove_bot_user(chat_id)
            failed_count += 1
            
        except RetryAfter as e:
            # Rate limit hit, wait and retry
            print(f"[BROADCAST] Rate limit hit, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                sent_count += 1
            except Exception as retry_error:
                print(f"[BROADCAST] Retry failed for {chat_id}: {retry_error}")
                failed_count += 1
                
        except TelegramError as e:
            # Other Telegram errors
            print(f"[BROADCAST] Error sending to {chat_id}: {e}")
            failed_count += 1
            
        except Exception as e:
            # Unexpected errors
            print(f"[BROADCAST] Unexpected error sending to {chat_id}: {e}")
            failed_count += 1
    
    # Final update
    db.update_broadcast_job(
        job_id,
        status='completed',
        sent_count=sent_count,
        failed_count=failed_count,
        completed=True
    )
    
    print(f"[BROADCAST] Job {job_id} completed: {sent_count} sent, {failed_count} failed")


def _broadcast_worker(job_id, users, message, bot_token):
    """
    Worker function to run broadcast in background thread.
    
    Args:
        job_id (int): Broadcast job ID
        users (list): List of users to broadcast to
        message (str): Message to send
        bot_token (str): Bot token
    """
    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(_send_broadcast_messages(job_id, users, message, bot_token))
    except Exception as e:
        print(f"[BROADCAST] Worker error: {e}")
        import traceback
        traceback.print_exc()
        
        # Mark job as failed
        import db
        db.update_broadcast_job(job_id, status='failed', completed=True)
    finally:
        loop.close()


def send_broadcast(users, message):
    """
    Send broadcast message to users asynchronously.
    Creates a job and returns immediately while processing in background.
    
    Args:
        users (list): List of user dicts with chat_id
        message (str): Message to broadcast
    
    Returns:
        dict: Job info with job_id and total_users
    """
    import db
    
    # Get bot token (prioritize production token)
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN_TEST')
    if not bot_token:
        raise ValueError("No bot token available for broadcasting")
    
    # Create broadcast job
    job_id = db.create_broadcast_job(message, 30, len(users))
    
    if not job_id:
        raise Exception("Failed to create broadcast job")
    
    # Start background worker
    worker_thread = threading.Thread(
        target=_broadcast_worker,
        args=(job_id, users, message, bot_token),
        daemon=True
    )
    worker_thread.start()
    
    return {
        'success': True,
        'job_id': job_id,
        'total_users': len(users),
        'status': 'processing'
    }


# Global persistent bot application and event loop for webhook mode
_bot_application = None
_bot_loop = None
_bot_thread = None


def start_webhook_bot(bot_token):
    """
    Start the Telegram bot in webhook mode with persistent event loop.
    This keeps the bot application alive to maintain conversation state.
    
    Args:
        bot_token (str): Telegram bot token
    """
    global _bot_application, _bot_loop, _bot_thread
    
    import asyncio
    import threading
    
    def run_event_loop():
        global _bot_loop
        _bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_bot_loop)
        _bot_loop.run_forever()
    
    # Start background event loop thread
    _bot_thread = threading.Thread(target=run_event_loop, daemon=True)
    _bot_thread.start()
    
    # Wait for loop to be ready
    import time
    while _bot_loop is None:
        time.sleep(0.01)
    
    # Initialize bot application on the loop
    async def init_app():
        global _bot_application
        _bot_application = create_bot_application(bot_token)
        await _bot_application.initialize()
        await _bot_application.start()
        print("[TELEGRAM] Webhook bot initialized and ready")
    
    asyncio.run_coroutine_threadsafe(init_app(), _bot_loop).result()


def handle_telegram_webhook(webhook_data, bot_token=None):
    """
    Handle incoming webhook from Telegram (for production).
    Forwards update to persistent bot application.
    
    Args:
        webhook_data (dict): Webhook payload from Telegram
        bot_token (str): Telegram bot token (optional, for compatibility)
        
    Returns:
        dict: Response status
    """
    import asyncio
    
    global _bot_application, _bot_loop
    
    print(f"[TELEGRAM] Webhook received: {webhook_data.get('update_id', 'unknown')}")
    
    try:
        if _bot_application is None or _bot_loop is None:
            print("[TELEGRAM] ERROR: Bot application not initialized")
            return {'status': 'error', 'message': 'Bot not initialized'}
        
        # Convert webhook data to Update object
        update = Update.de_json(webhook_data, _bot_application.bot)
        
        if update:
            msg_text = update.message.text if update.message else (update.callback_query.data if update.callback_query else 'unknown')
            print(f"[TELEGRAM] Processing update: {msg_text}")
            
            # Forward update to persistent bot application
            future = asyncio.run_coroutine_threadsafe(
                _bot_application.process_update(update),
                _bot_loop
            )
            
            # Wait for processing to complete (with timeout)
            future.result(timeout=30)
            print("[TELEGRAM] Update processed successfully")
        
        return {'status': 'ok'}
        
    except Exception as e:
        print(f"[TELEGRAM] Webhook processing error: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}


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
    # Use production token first, fall back to test token
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN_TEST')
    
    if not bot_token:
        print("ERROR: No bot token found. Set TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN_TEST")
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
