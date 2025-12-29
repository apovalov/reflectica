"""Helpers that send single-entry summaries similar to the weekly export."""
from __future__ import annotations

import os
import uuid

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.db.models import Event, User
from app.db.session import get_session
from app.utils.logging import logger
from app.utils.timezone import get_user_timezone, utc_to_local


def _format_event_summary(event: Event, timezone):
    """Build the markdown-style block for a single event."""
    local_dt = utc_to_local(event.created_at_utc, timezone)
    time_str = local_dt.strftime("%H:%M")
    lines = [
        "# Mindforms Diary - Week Summary",
        "",
        f"## {event.local_date}",
        "",
        f"### {event.event_type.capitalize()} ({event.source_type}) - {time_str}",
        event.text_content or "*Processing...*",
    ]
    return "\n".join(lines)


async def send_entry_summary(event_id: str | uuid.UUID):
    """Send the diary entry summary to the user who created the event."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, cannot send entry summaries")
        return

    session = get_session().__enter__()
    try:
        event = session.query(Event).filter(Event.id == uuid.UUID(str(event_id))).first()
        if not event:
            logger.error("Cannot find event %s to send summary", event_id)
            return

        if not event.text_content:
            logger.debug("Event %s has no text_content yet, skipping summary", event_id)
            return

        user = session.query(User).filter(User.telegram_user_id == event.telegram_user_id).first()
        timezone = get_user_timezone(user.timezone if user else None)
        chat_id = event.chat_id
        summary = _format_event_summary(event, timezone)
    finally:
        session.close()

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"<pre>{summary}</pre>",
        )
    except Exception as exc:
        logger.error("Failed to send entry summary for %s: %s", event_id, exc)
    finally:
        await bot.session.close()
