"""
Dependency Sanity Check

Fails loudly if the wrong telegram package is installed.
The 'telegram' package (0.0.1) is a stub that shadows python-telegram-bot
and breaks all Telegram bot functionality.

Run: pytest tests/test_dependency_sanity.py -v
"""

import importlib.metadata
import sys


def test_correct_telegram_library_installed():
    """
    Verify python-telegram-bot is installed, NOT the stub 'telegram' package.
    
    The wrong package causes:
    - ImportError: cannot import name 'Update' from 'telegram'
    - ImportError: cannot import name 'Bot' from 'telegram'
    """
    try:
        ptb_version = importlib.metadata.version("python-telegram-bot")
    except importlib.metadata.PackageNotFoundError:
        raise AssertionError(
            "MISSING DEPENDENCY: python-telegram-bot is not installed!\n"
            "Run: pip install python-telegram-bot[rate-limiter]"
        )
    
    try:
        bad_telegram_version = importlib.metadata.version("telegram")
        if bad_telegram_version == "0.0.1":
            raise AssertionError(
                f"WRONG PACKAGE INSTALLED: 'telegram' version {bad_telegram_version} detected!\n"
                "This stub package shadows python-telegram-bot and breaks imports.\n"
                "Fix: pip uninstall telegram && pip install python-telegram-bot[rate-limiter] --force-reinstall"
            )
    except importlib.metadata.PackageNotFoundError:
        pass
    
    from telegram import Update, Bot
    
    assert Update is not None, "telegram.Update should be importable"
    assert Bot is not None, "telegram.Bot should be importable"
    
    print(f"✅ python-telegram-bot {ptb_version} correctly installed")


def test_telegram_imports_work():
    """
    Verify critical Telegram imports work correctly.
    These imports fail if the wrong 'telegram' package is installed.
    """
    try:
        from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import Application, CommandHandler, CallbackQueryHandler
    except ImportError as e:
        raise AssertionError(
            f"Telegram imports failed: {e}\n"
            "This usually means the wrong 'telegram' package (0.0.1) is installed.\n"
            "Fix: pip uninstall telegram && pip install python-telegram-bot[rate-limiter] --force-reinstall"
        )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
