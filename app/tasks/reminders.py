"""Celery tasks for sending reminders."""
import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Event, Reminder, User
from app.db.session import get_session
from app.tasks.celery_app import celery_app
from app.utils.logging import logger
from app.utils.timezone import get_user_timezone, is_time_in_range


async def _send_reminders_async():
    """Async helper to send reminders."""
    session = None
    bot = None
    try:
        session = get_session().__enter__()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set")
            return

        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        # Get all users
        users = session.query(User).all()
        now_utc = datetime.now(ZoneInfo("UTC"))

        for user in users:
            try:
                user_tz = get_user_timezone(user.timezone)
                local_now = now_utc.astimezone(user_tz)
                local_time = local_now.time()
                local_date = local_now.date()

                # Check if current time is in reminder window
                if not is_time_in_range(local_time, user.reminder_time_local, window_minutes=5):
                    continue

                # Check each required type
                for required_type in user.reminder_required_types:
                    # Check if reminder already sent today
                    existing_reminder = (
                        session.query(Reminder)
                        .filter(
                            Reminder.telegram_user_id == user.telegram_user_id,
                            Reminder.local_date == local_date,
                            Reminder.event_type == required_type,
                        )
                        .first()
                    )

                    if existing_reminder:
                        continue

                    # Check if event exists for today
                    event_exists = (
                        session.query(Event)
                        .filter(
                            Event.telegram_user_id == user.telegram_user_id,
                            Event.local_date == local_date,
                            Event.event_type == required_type,
                        )
                        .first()
                    )

                    if not event_exists:
                        # Send reminder
                        type_display = required_type.capitalize()
                        message = (
                            f"You haven't logged <b>{type_display}</b> today. "
                            f"Want to add it now?"
                        )

                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text=f"Add {required_type}",
                                        callback_data=f"add_{required_type}",
                                    )
                                ]
                            ]
                        )

                        try:
                            await bot.send_message(
                                chat_id=user.telegram_user_id,
                                text=message,
                                reply_markup=keyboard,
                            )

                            # Record reminder
                            reminder = Reminder(
                                telegram_user_id=user.telegram_user_id,
                                local_date=local_date,
                                event_type=required_type,
                                status="sent",
                            )
                            session.add(reminder)
                            session.commit()

                            logger.info(
                                f"Sent reminder for {required_type} to user {user.telegram_user_id}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send reminder to user {user.telegram_user_id}: {e}"
                            )

            except Exception as e:
                logger.error(f"Error processing user {user.telegram_user_id}: {e}", exc_info=True)
                continue

    except Exception as e:
        logger.error(f"Error in send_due_reminders_task: {e}", exc_info=True)
    finally:
        if bot:
            await bot.session.close()
        if session:
            session.close()


@celery_app.task(name="send_due_reminders")
def send_due_reminders_task():
    """Send reminders to users who haven't completed required entries today."""
    asyncio.run(_send_reminders_async())

