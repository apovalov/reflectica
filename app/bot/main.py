"""Main entry point for Telegram bot."""
import asyncio
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.bot.handlers import router
from app.utils.logging import logger

# Load environment variables
load_dotenv()


async def main():
    """Main function to run the bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
        sys.exit(1)

    # Create bot and dispatcher
    bot = Bot(token=bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Register router
    dp.include_router(router)

    # Start polling
    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)

