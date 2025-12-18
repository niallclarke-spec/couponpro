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
    ChatMemberHandler,
    filters,
    ContextTypes,
    AIORateLimiter
)
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram_image_gen import generate_promo_image
import coupon_validator
from coupon_validator import coupon_cache_lock

# Conversation states
WAITING_FOR_COUPON = 1

# Coupon cache: maps chat_id -> coupon_code
# This allows server.py to track usage synchronously from webhook
coupon_cache = {}

# Index cache for template data
INDEX_CACHE = {
    'data': None,
    'expires_at': 0
}
CACHE_TTL = 300


def get_templates():
    """
    Fetch templates from index.json (cached) and filter for Telegram-enabled only.
    
    Returns:
        list: List of template dicts with keys: slug, name, square, story (only telegramEnabled=true)
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
        
        all_templates = INDEX_CACHE['data'].get('templates', [])
        
        # Filter for Telegram-enabled templates (default to true for backward compatibility)
        telegram_templates = [t for t in all_templates if t.get('telegramEnabled', True) is not False]
        
        print(f"[TELEGRAM] Returning {len(telegram_templates)}/{len(all_templates)} telegram-enabled templates")
        return telegram_templates
        
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
    import sys
    print(f"[COUPON-HANDLER] ⚡ handle_coupon_input called!", flush=True)
    sys.stdout.flush()
    
    coupon_code = update.message.text.strip().upper()
    chat_id = update.effective_chat.id
    
    print(f"[COUPON-HANDLER] Processing coupon: {coupon_code}, chat_id: {chat_id}", flush=True)
    sys.stdout.flush()
    
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
            await _log_usage(chat_id, None, coupon_code, False, 'invalid_coupon')
            return WAITING_FOR_COUPON
        
    except Exception as val_error:
        print(f"[TELEGRAM] Coupon validation error: {val_error}")
        await update.message.reply_text(
            f"⚠️ Unable to validate coupon. Please try again later."
        )
        await _log_usage(chat_id, None, coupon_code, False, 'validation_error')
        return WAITING_FOR_COUPON
    
    # Coupon is valid - store in cache (survives after ConversationHandler.END)
    with coupon_cache_lock:
        coupon_cache[chat_id] = coupon_code
    print(f"[COUPON-HANDLER] ✅ Stored coupon '{coupon_code}' in cache for chat_id {chat_id}", flush=True)
    sys.stdout.flush()
    
    # Track user for broadcast capability (CRITICAL: must complete for DB fallback to work)
    try:
        import db
        # Extract user profile data from Telegram
        user = update.effective_user
        username = user.username if user else None
        first_name = user.first_name if user else None
        last_name = user.last_name if user else None
        
        await asyncio.to_thread(db.track_bot_user, chat_id, coupon_code, username, first_name, last_name)
        print(f"[TELEGRAM] ✅ User {chat_id} tracked successfully in database (username={username}, name={first_name} {last_name})", flush=True)
        sys.stdout.flush()
    except Exception as track_error:
        print(f"[TELEGRAM] ⚠️ WARNING: Failed to track user {chat_id}: {track_error}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        # Continue anyway - user can still use bot with in-memory cache
    
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
        await _log_usage(chat_id, None, coupon_code, False, 'templates_error')
        return ConversationHandler.END
    
    # Send each template with preview image and button
    for template in templates:
        template_name = template.get('name', template.get('slug', 'Template'))
        template_slug = template.get('slug')
        preview_url = template.get('square') or template.get('story')
        
        # Create button for this template
        keyboard = [[InlineKeyboardButton(
            "👉 GENERATE 👈",
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
    
    # Send final confirmation message
    await update.message.reply_text(
        f"✅ Coupon *{coupon_code}* is valid!\n\nClick any template above to generate your promo image.",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END


async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle template button click - generate and send image.
    """
    import sys
    
    query = update.callback_query
    await query.answer()
    
    handler_msg = f"[HANDLER] handle_template_selection called! data={query.data}"
    print(handler_msg, flush=True)
    sys.stdout.flush()
    
    chat_id = update.effective_chat.id
    
    # Get coupon from cache (source of truth in webhook mode)
    with coupon_cache_lock:
        coupon_code = coupon_cache.get(chat_id)
    
    # If cache miss, try DB fallback
    if not coupon_code:
        print(f"[HANDLER] Cache miss for chat_id={chat_id}, trying DB fallback", flush=True)
        sys.stdout.flush()
        try:
            import db
            bot_user = await asyncio.to_thread(db.get_bot_user, chat_id)
            if bot_user and bot_user.get('last_coupon_code'):
                coupon_code = bot_user['last_coupon_code']
                # Repopulate cache
                with coupon_cache_lock:
                    coupon_cache[chat_id] = coupon_code
                print(f"[HANDLER] ✅ Restored coupon from DB: {coupon_code}", flush=True)
                sys.stdout.flush()
        except Exception as e:
            print(f"[HANDLER] DB fallback failed: {e}", flush=True)
            sys.stdout.flush()
    
    print(f"[HANDLER] chat_id={chat_id}, coupon_code={coupon_code}", flush=True)
    sys.stdout.flush()
    
    if not coupon_code:
        err_msg = f"[HANDLER] ERROR: No coupon code found in cache or DB"
        print(err_msg, flush=True)
        sys.stdout.flush()
        await query.message.reply_text("Please start over with /start")
        return
    
    code_msg = f"[HANDLER] Coupon code: {coupon_code}"
    print(code_msg, flush=True)
    sys.stdout.flush()
    
    # Parse callback data
    callback_data = query.data
    if not callback_data.startswith('template:'):
        return
    
    template_selection = callback_data.replace('template:', '')
    
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
    import sys
    
    msg = f"[TELEGRAM] _generate_and_send called: template={template_slug}, coupon={coupon_code}, chat_id={chat_id}"
    print(msg, flush=True)
    sys.stdout.flush()
    
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
            print(f"[TELEGRAM] About to log FAILED usage: chat_id={chat_id}, error={error}", flush=True)
            sys.stdout.flush()
            await _log_usage(chat_id, template_slug, coupon_code, False, error)
            print(f"[TELEGRAM] Finished logging FAILED usage", flush=True)
            sys.stdout.flush()
            return
        
        # Send to Telegram
        await message.reply_photo(photo=image_bio, filename=f'{template_slug}-{coupon_code}.png')
        print(f"[TELEGRAM] About to log SUCCESS usage: chat_id={chat_id}", flush=True)
        sys.stdout.flush()
        await _log_usage(chat_id, template_slug, coupon_code, True, None)
        print(f"[TELEGRAM] Finished logging SUCCESS usage", flush=True)
        sys.stdout.flush()
        
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
        await _log_usage(chat_id, template_slug, coupon_code, False, 'generation_failed')


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
    chat_id = update.effective_chat.id
    
    # Try cache first
    with coupon_cache_lock:
        coupon_code = coupon_cache.get(chat_id)
    
    # If cache miss, try DB fallback
    if not coupon_code:
        try:
            import db
            bot_user = await asyncio.to_thread(db.get_bot_user, chat_id)
            if bot_user and bot_user.get('last_coupon_code'):
                coupon_code = bot_user['last_coupon_code']
                # Repopulate cache
                with coupon_cache_lock:
                    coupon_cache[chat_id] = coupon_code
                print(f"[GENERATE] ✅ Restored coupon from DB: {coupon_code}")
        except Exception as e:
            print(f"[GENERATE] DB fallback failed: {e}")
    
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
            "👉 GENERATE 👈",
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
    
    # Send confirmation message
    await update.message.reply_text(
        f"✅ Select a template above to generate with coupon *{coupon_code}*",
        parse_mode='Markdown'
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel command - exit conversation."""
    await update.message.reply_text("Conversation cancelled. Use /start to begin again.")
    return ConversationHandler.END


async def _log_usage(chat_id, template_slug, coupon_code, success, error_type, device_type='unknown'):
    """
    Internal helper to log bot usage. Silently fails to avoid disrupting bot.
    Runs in background thread to avoid blocking event loop.
    
    Args:
        device_type (str): Device type - Telegram Bot API does not provide device information, 
                          so this will always be 'unknown' for Telegram bot usage
    """
    import asyncio
    import sys
    import traceback
    try:
        print(f"[BOT_USAGE] Attempting to log: chat_id={chat_id}, template={template_slug}, coupon={coupon_code}, success={success}, device={device_type}", flush=True)
        sys.stdout.flush()
        import db
        if chat_id:
            await asyncio.to_thread(db.log_bot_usage, chat_id, template_slug, coupon_code, success, error_type, device_type)
            print(f"[BOT_USAGE] ✅ Successfully logged usage to database", flush=True)
            sys.stdout.flush()
        else:
            print(f"[BOT_USAGE] ⚠️ No chat_id provided - skipped logging", flush=True)
            sys.stdout.flush()
    except Exception as e:
        print(f"[BOT_USAGE] ❌ ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()


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
    # Create application with rate limiting and automatic retries
    rate_limiter = AIORateLimiter(
        overall_max_rate=25,  # 25 msg/sec (safe buffer below Telegram's 30/s limit)
        max_retries=3  # Automatically retry failed requests up to 3 times
    )
    
    application = (
        Application.builder()
        .token(bot_token)
        .concurrent_updates(False)  # Required for ConversationHandler
        .rate_limiter(rate_limiter)
        .post_init(post_init)
        .build()
    )
    
    # Define conversation handler (no persistence needed - using coupon_cache)
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
    
    # Fallback handler: treat any plain text as coupon input (outside conversation)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coupon_input))
    
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
    
    # Update job status to processing (non-blocking)
    await asyncio.to_thread(db.update_broadcast_job, job_id, status='processing')
    
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
            
            # Update progress every 10 messages (non-blocking)
            if sent_count % 10 == 0:
                await asyncio.to_thread(db.update_broadcast_job, job_id, sent_count=sent_count, failed_count=failed_count)
            
            # Rate limit
            await asyncio.sleep(rate_limit_delay)
            
        except Forbidden:
            # User blocked the bot - remove them (non-blocking)
            print(f"[BROADCAST] User {chat_id} blocked bot, removing")
            await asyncio.to_thread(db.remove_bot_user, chat_id)
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
    
    # Final update (non-blocking)
    await asyncio.to_thread(
        db.update_broadcast_job,
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


def send_broadcast(users, message, tenant_id='entrylab'):
    """
    Send broadcast message to users asynchronously.
    Creates a job and returns immediately while processing in background.
    
    Args:
        users (list): List of user dicts with chat_id
        message (str): Message to broadcast
        tenant_id (str): Tenant ID for bot credentials (defaults to 'entrylab')
    
    Returns:
        dict: Job info with job_id and total_users
        
    Raises:
        ValueError: If bot token not configured for tenant
    """
    import db
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
    
    # Get bot token from database
    try:
        creds = get_bot_credentials(tenant_id, 'message')
        bot_token = creds['bot_token']
    except BotNotConfiguredError as e:
        raise ValueError(f"No bot token available for broadcasting: {e}")
    
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
        
        # Configure webhook URL with Telegram
        webhook_url = os.getenv('WEBHOOK_URL', 'https://dash.promostack.io/api/telegram-webhook')
        try:
            await _bot_application.bot.set_webhook(webhook_url)
            print(f"[TELEGRAM] ✅ Webhook configured: {webhook_url}")
        except Exception as e:
            print(f"[TELEGRAM] ⚠️ Failed to set webhook: {e}")
        
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
    import sys
    
    global _bot_application, _bot_loop
    
    msg = f"[WEBHOOK] Received update_id: {webhook_data.get('update_id', 'unknown')}"
    print(msg, flush=True)
    sys.stdout.flush()
    
    try:
        if _bot_application is None or _bot_loop is None:
            err = "[WEBHOOK] ERROR: Bot application not initialized"
            print(err, flush=True)
            sys.stdout.flush()
            return {'status': 'error', 'message': 'Bot not initialized'}
        
        # Convert webhook data to Update object
        try:
            update = Update.de_json(webhook_data, _bot_application.bot)
        except Exception as de_json_error:
            print(f"[WEBHOOK] ❌ Failed to deserialize update: {de_json_error}", flush=True)
            # Telegram expects 200 OK even on errors
            return {'status': 'error', 'message': str(de_json_error)}
        
        if update:
            msg_text = update.message.text if update.message else (update.callback_query.data if update.callback_query else 'unknown')
            processing = f"[WEBHOOK] Processing: type={type(update.message or update.callback_query).__name__}, text={msg_text}"
            print(processing, flush=True)
            sys.stdout.flush()
            
            try:
                # Forward update to persistent bot application
                future = asyncio.run_coroutine_threadsafe(
                    _bot_application.process_update(update),
                    _bot_loop
                )
                
                # Wait for processing to complete (with timeout)
                future.result(timeout=30)
                success = "[WEBHOOK] ✅ Update processed successfully"
                print(success, flush=True)
                sys.stdout.flush()
            except Exception as proc_error:
                error_msg = f"[WEBHOOK] ❌ Error processing update: {proc_error}"
                print(error_msg, flush=True)
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
        
        return {'status': 'ok'}
        
    except Exception as e:
        print(f"[TELEGRAM] Webhook processing error: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}


async def create_private_channel_invite_link(channel_id):
    """
    Create a unique invite link for the private Telegram channel.
    Uses forex bot token (entrylab_bot in prod, test bot in dev).
    
    Args:
        channel_id (int|str): Telegram channel ID (e.g., -1003213499920)
    
    Returns:
        str: Invite link URL or None if error
    """
    try:
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_token = creds['bot_token']
        except BotNotConfiguredError as e:
            print(f"[TELEGRAM] ERROR: Forex bot not configured: {e}")
            return None
        
        if not forex_token:
            print("[TELEGRAM] ERROR: Forex bot token not set, cannot create invite link")
            return None
        
        from telegram import Bot
        bot = Bot(token=forex_token)
        
        # Create invite link with member limit (1) - single-use link
        # This ensures each link is unique and can be tracked
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,  # Single-use link
            name="EntryLab Subscription"
        )
        
        print(f"[TELEGRAM] Created invite link: {invite_link.invite_link}")
        return invite_link.invite_link
        
    except Exception as e:
        print(f"[TELEGRAM] Error creating invite link: {e}")
        import traceback
        traceback.print_exc()
        return None


async def kick_user_from_channel(channel_id, user_id):
    """
    Remove a user from the private Telegram channel.
    Uses forex bot token (entrylab_bot in prod, test bot in dev).
    
    Args:
        channel_id (int|str): Telegram channel ID
        user_id (int): Telegram user ID to kick
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_token = creds['bot_token']
        except BotNotConfiguredError as e:
            print(f"[TELEGRAM] ERROR: Forex bot not configured: {e}")
            return False
        
        if not forex_token:
            print("[TELEGRAM] ERROR: Forex bot token not set, cannot kick user")
            return False
        
        from telegram import Bot
        bot = Bot(token=forex_token)
        
        # Ban user (this kicks them out)
        await bot.ban_chat_member(
            chat_id=channel_id,
            user_id=user_id
        )
        
        # Unban immediately so they can be re-added later if they resubscribe
        await bot.unban_chat_member(
            chat_id=channel_id,
            user_id=user_id
        )
        
        print(f"[TELEGRAM] Kicked user {user_id} from channel {channel_id}")
        return True
        
    except Exception as e:
        print(f"[TELEGRAM] Error kicking user: {e}")
        import traceback
        traceback.print_exc()
        return False


async def check_user_in_channel(channel_id, user_id):
    """
    Check if a user is a member of the channel.
    Uses forex bot token (entrylab_bot in prod, test bot in dev).
    
    Args:
        channel_id (int|str): Telegram channel ID
        user_id (int): Telegram user ID
    
    Returns:
        dict: {'is_member': bool, 'status': str} or None if error
    """
    try:
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_token = creds['bot_token']
        except BotNotConfiguredError as e:
            print(f"[TELEGRAM] ERROR: Forex bot not configured: {e}")
            return None
        
        if not forex_token:
            print("[TELEGRAM] ERROR: Forex bot token not set, cannot check user")
            return None
        
        from telegram import Bot
        bot = Bot(token=forex_token)
        
        member = await bot.get_chat_member(
            chat_id=channel_id,
            user_id=user_id
        )
        
        # Member status can be: 'creator', 'administrator', 'member', 'restricted', 'left', 'kicked'
        is_member = member.status in ['creator', 'administrator', 'member', 'restricted']
        
        return {
            'is_member': is_member,
            'status': member.status
        }
        
    except Exception as e:
        print(f"[TELEGRAM] Error checking user membership: {e}")
        return None


def sync_create_private_channel_invite_link(channel_id):
    """Synchronous wrapper for creating invite links (for use in HTTP handlers)"""
    if _bot_loop is None:
        print("[TELEGRAM] ERROR: Bot loop not initialized")
        return None
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            create_private_channel_invite_link(channel_id),
            _bot_loop
        )
        return future.result(timeout=10)
    except Exception as e:
        print(f"[TELEGRAM] Error in sync_create_private_channel_invite_link: {e}")
        return None


def sync_kick_user_from_channel(channel_id, user_id):
    """Synchronous wrapper for kicking users (for use in HTTP handlers)"""
    if _bot_loop is None:
        print("[TELEGRAM] ERROR: Bot loop not initialized")
        return False
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            kick_user_from_channel(channel_id, user_id),
            _bot_loop
        )
        return future.result(timeout=10)
    except Exception as e:
        print(f"[TELEGRAM] Error in sync_kick_user_from_channel: {e}")
        return False


def sync_check_user_in_channel(channel_id, user_id):
    """Synchronous wrapper for checking user membership (for use in HTTP handlers)"""
    if _bot_loop is None:
        print("[TELEGRAM] ERROR: Bot loop not initialized")
        return None
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            check_user_in_channel(channel_id, user_id),
            _bot_loop
        )
        return future.result(timeout=10)
    except Exception as e:
        print(f"[TELEGRAM] Error in sync_check_user_in_channel: {e}")
        return None


async def send_message_to_user(user_id, message, parse_mode='Markdown'):
    """Send a direct message to a user via the Forex/EntryLab bot"""
    try:
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            bot_token = creds['bot_token']
        except BotNotConfiguredError as e:
            print(f"[TELEGRAM] ERROR: Forex bot not configured: {e}")
            return False
        
        if not bot_token:
            print("[TELEGRAM] ERROR: No forex bot token available")
            return False
        
        from telegram import Bot
        bot = Bot(token=bot_token)
        
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode=parse_mode
        )
        print(f"[TELEGRAM] Sent message to user {user_id}")
        return True
    except Exception as e:
        print(f"[TELEGRAM] Error sending message to user {user_id}: {e}")
        return False


def sync_send_message(user_id, message, parse_mode='Markdown'):
    """Synchronous wrapper for sending messages (for use in HTTP handlers)"""
    if _bot_loop is None:
        print("[TELEGRAM] ERROR: Bot loop not initialized")
        return False
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            send_message_to_user(user_id, message, parse_mode),
            _bot_loop
        )
        return future.result(timeout=10)
    except Exception as e:
        print(f"[TELEGRAM] Error in sync_send_message: {e}")
        return False


async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle chat member updates (joins, leaves, etc.) in the forex signals channel.
    
    This function is triggered when a user joins the private forex channel and
    automatically links their Telegram user ID to their subscription record.
    
    NOTE: Chat member updates must be enabled in BotFather settings:
    /setprivacy -> Disable (to receive all messages)
    OR bot must be admin in the channel to receive member updates
    """
    try:
        if not update.chat_member:
            return
        
        chat_member_update = update.chat_member
        
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_channel_id = creds['channel_id']
        except BotNotConfiguredError:
            return
        
        if not forex_channel_id:
            return
        
        try:
            forex_channel_id = int(forex_channel_id)
        except (ValueError, TypeError):
            print(f"[JOIN_TRACKER] Invalid channel_id format: {forex_channel_id}")
            return
        
        if chat_member_update.chat.id != forex_channel_id:
            return
        
        old_status = chat_member_update.old_chat_member.status
        new_status = chat_member_update.new_chat_member.status
        
        # Check if this is a join event (user was not a member, now is a member)
        # Member statuses: 'member', 'administrator', 'creator'
        # Non-member statuses: 'left', 'kicked', 'restricted'
        is_join = (old_status in ['left', 'kicked', 'restricted']) and (new_status in ['member', 'administrator', 'creator'])
        
        if not is_join:
            return
        
        # Extract user information
        user = chat_member_update.new_chat_member.user
        telegram_user_id = user.id
        telegram_username = user.username if user.username else None
        
        # Extract invite link if available (may be None)
        invite_link = None
        if hasattr(chat_member_update, 'invite_link') and chat_member_update.invite_link:
            invite_link = chat_member_update.invite_link.invite_link
        
        # Get join timestamp
        from datetime import datetime
        joined_at = datetime.utcnow()
        
        print(f"[JOIN_TRACKER] User joined: {telegram_user_id} (@{telegram_username}), invite_link: {invite_link}")
        
        # Link to subscription in database (run in thread to avoid blocking event loop)
        import db
        result = await asyncio.to_thread(
            db.link_subscription_to_telegram_user,
            invite_link,
            telegram_user_id,
            telegram_username,
            joined_at
        )
        
        if result:
            print(f"[JOIN_TRACKER] ✅ Successfully linked user {telegram_user_id} to subscription {result['email']}")
        else:
            print(f"[JOIN_TRACKER] ⚠️ Could not link user {telegram_user_id} (@{telegram_username}) - no matching pending subscription")
        
    except Exception as e:
        print(f"[JOIN_TRACKER] ❌ Error handling chat member update: {e}")
        import traceback
        traceback.print_exc()


async def start_join_tracking():
    """
    Start the Telegram bot join tracking for the forex signals channel.
    
    This function creates a separate bot application that monitors member joins
    in the private forex signals channel and automatically links Telegram user IDs
    to subscription records.
    
    Requirements:
    - Bot credentials must be configured in database (tenant_bot_connections table)
    - Bot must be admin in the channel to receive chat member updates
    - Chat member updates must be enabled in BotFather settings
    
    This runs independently via polling in a background task.
    """
    try:
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_bot_token = creds['bot_token']
            forex_channel_id = creds['channel_id']
        except BotNotConfiguredError as e:
            print(f"[JOIN_TRACKER] ⚠️ Forex bot not configured: {e} - join tracking disabled")
            return
        
        if not forex_bot_token:
            print("[JOIN_TRACKER] ⚠️ Bot token not configured - join tracking disabled")
            return
        
        if not forex_channel_id:
            print("[JOIN_TRACKER] ⚠️ Channel ID not configured - join tracking disabled")
            return
        
        print("[JOIN_TRACKER] Initializing join tracking bot...")
        print(f"[JOIN_TRACKER] Monitoring channel: {forex_channel_id}")
        print("[JOIN_TRACKER] NOTE: Bot must be admin in channel and chat member updates must be enabled in BotFather")
        
        # Create application
        application = (
            Application.builder()
            .token(forex_bot_token)
            .build()
        )
        
        # Add chat member handler
        application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
        
        print("[JOIN_TRACKER] ✅ Join tracking bot initialized, starting polling...")
        
        # Initialize and start the application manually (avoids signal handler issues in threads)
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=['chat_member'])
        
        print("[JOIN_TRACKER] ✅ Join tracking bot is now running")
        
        # Keep the bot running indefinitely
        while True:
            await asyncio.sleep(3600)
        
    except Exception as e:
        print(f"[JOIN_TRACKER] ❌ Error starting join tracking: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean shutdown
        try:
            if 'application' in locals():
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
        except Exception as cleanup_error:
            print(f"[JOIN_TRACKER] Error during cleanup: {cleanup_error}")


def handle_forex_webhook(webhook_data: dict, bot_token: str) -> dict:
    """
    Handle incoming webhook updates for the forex bot (join tracking and user messages).
    
    This handles:
    - chat_member updates when users join/leave the forex signals channel
    - message updates when users send messages to the bot (responds with support email)
    Uses webhooks instead of polling to avoid conflicts with production server.
    
    Args:
        webhook_data: The raw webhook data from Telegram
        bot_token: The forex bot token
        
    Returns:
        dict with success status
    """
    try:
        # Handle user messages - respond with support email
        if 'message' in webhook_data:
            message_data = webhook_data['message']
            chat_id = message_data.get('chat', {}).get('id')
            chat_type = message_data.get('chat', {}).get('type', 'private')
            
            # Only respond to private messages (not group/channel messages)
            if chat_type == 'private' and chat_id:
                try:
                    import requests
                    support_message = (
                        "👋 *Hello!*\n\n"
                        "For subscription support, billing questions, or cancellation requests, "
                        "please email us at:\n\n"
                        "📧 *members@entrylab.io*\n\n"
                        "Our team will get back to you within 24 hours."
                    )
                    
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    response = requests.post(url, json={
                        'chat_id': chat_id,
                        'text': support_message,
                        'parse_mode': 'Markdown'
                    }, timeout=10)
                    
                    if response.json().get('ok'):
                        print(f"[FOREX_BOT] Sent support email response to user {chat_id}")
                        return {'success': True, 'message': f'Sent support response to {chat_id}'}
                    else:
                        print(f"[FOREX_BOT] Failed to send response: {response.json()}")
                except Exception as msg_error:
                    print(f"[FOREX_BOT] Error sending support response: {msg_error}")
            
            return {'success': True, 'message': 'Message handled'}
        
        # Check if this is a chat_member update
        if 'chat_member' not in webhook_data:
            return {'success': True, 'message': 'Not a chat_member update, ignored'}
        
        chat_member_data = webhook_data['chat_member']
        
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials('entrylab', 'signal_bot')
            forex_channel_id = creds['channel_id']
        except BotNotConfiguredError as e:
            return {'success': False, 'error': f'Forex bot not configured: {e}'}
        
        if not forex_channel_id:
            return {'success': False, 'error': 'Channel ID not configured in database'}
        
        try:
            forex_channel_id = int(forex_channel_id)
        except (ValueError, TypeError):
            return {'success': False, 'error': f'Invalid channel_id: {forex_channel_id}'}
        
        # Check if this is for our channel
        chat_id = chat_member_data.get('chat', {}).get('id')
        if chat_id != forex_channel_id:
            return {'success': True, 'message': f'Not our channel ({chat_id}), ignored'}
        
        # Extract old and new status
        old_status = chat_member_data.get('old_chat_member', {}).get('status', 'left')
        new_status = chat_member_data.get('new_chat_member', {}).get('status', 'left')
        
        # Check if this is a join event
        is_join = (old_status in ['left', 'kicked', 'restricted']) and (new_status in ['member', 'administrator', 'creator'])
        
        if not is_join:
            print(f"[JOIN_TRACKER] Status change: {old_status} -> {new_status} (not a join)")
            return {'success': True, 'message': f'Status change {old_status} -> {new_status}, not a join'}
        
        # Extract user information
        user_data = chat_member_data.get('new_chat_member', {}).get('user', {})
        telegram_user_id = user_data.get('id')
        telegram_username = user_data.get('username')
        
        # Extract invite link if available
        invite_link = None
        invite_link_data = chat_member_data.get('invite_link')
        if invite_link_data:
            invite_link = invite_link_data.get('invite_link')
        
        from datetime import datetime
        joined_at = datetime.utcnow()
        
        print(f"[JOIN_TRACKER] User joined: {telegram_user_id} (@{telegram_username}), invite_link: {invite_link}")
        
        # Link to subscription in database
        import db
        result = db.link_subscription_to_telegram_user(
            invite_link,
            telegram_user_id,
            telegram_username,
            joined_at
        )
        
        if result:
            print(f"[JOIN_TRACKER] ✅ Successfully linked user {telegram_user_id} to subscription {result['email']}")
            return {'success': True, 'message': f'Linked user {telegram_user_id} to {result["email"]}'}
        else:
            print(f"[JOIN_TRACKER] ⚠️ Could not link user {telegram_user_id} (@{telegram_username}) - no matching pending subscription")
            return {'success': True, 'message': f'User {telegram_user_id} joined but no matching subscription found'}
        
    except Exception as e:
        print(f"[JOIN_TRACKER] ❌ Error handling forex webhook: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


def setup_forex_webhook(bot_token: str, webhook_url: str) -> bool:
    """
    Set up webhook for the forex bot to receive chat_member updates.
    
    Args:
        bot_token: The forex bot token
        webhook_url: The full URL for the webhook endpoint
        
    Returns:
        bool: True if webhook was set successfully
    """
    import requests
    
    try:
        # Set webhook via Telegram API
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        params = {
            'url': webhook_url,
            'allowed_updates': ['chat_member', 'message']  # Receive chat_member and message updates
        }
        
        response = requests.post(url, json=params, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            print(f"[JOIN_TRACKER] ✅ Webhook configured: {webhook_url}")
            return True
        else:
            print(f"[JOIN_TRACKER] ❌ Failed to set webhook: {result.get('description')}")
            return False
            
    except Exception as e:
        print(f"[JOIN_TRACKER] ❌ Error setting up webhook: {e}")
        return False


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
    from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
    
    # Get bot token from database (default to entrylab tenant)
    tenant_id = os.getenv('TENANT_ID', 'entrylab')
    
    try:
        creds = get_bot_credentials(tenant_id, 'message')
        bot_token = creds['bot_token']
    except BotNotConfiguredError as e:
        print(f"ERROR: {e}")
        print(f"Please configure the message bot in the database for tenant '{tenant_id}'")
        bot_token = None
    
    if not bot_token:
        print("ERROR: No bot token found. Configure bot credentials in database.")
    else:
        print("=" * 60)
        print("PromoStack Conversational Telegram Bot")
        print("=" * 60)
        print(f"\nTenant: {tenant_id}")
        print("\nConversational flow:")
        print("1. User: /start")
        print("2. Bot: Please enter your FunderPro coupon code")
        print("3. User: WELCOME30")
        print("4. Bot: ✅ Coupon valid! [Shows template buttons]")
        print("5. User: Clicks template button")
        print("6. Bot: Generates and sends image")
        print("\n" + "=" * 60)
        run_bot(bot_token)
