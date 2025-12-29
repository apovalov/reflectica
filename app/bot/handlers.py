"""Telegram bot handlers."""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import redis
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PhotoSize, Voice

from app.db.models import Event, User
from app.db.session import get_session
from app.gemini.client import GeminiClient
from app.storage.minio_client import MinIOClient
from app.tasks.processing import analyze_face_task, ocr_handwriting_task, transcribe_audio_task
from app.utils.file_utils import download_file_to_temp, get_file_extension, auto_rotate_image
from app.utils.logging import logger
from app.utils.timezone import get_user_timezone, get_local_date, utc_to_local
from app.bot.keyboards import get_event_type_keyboard

router = Router()

# Redis for pending type storage
redis_client = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))


def get_pending_type_key(telegram_user_id: int) -> str:
    """Get Redis key for pending event type."""
    return f"pending_type:{telegram_user_id}"


def get_pending_message_key(telegram_user_id: int) -> str:
    """Get Redis key for pending message data."""
    return f"pending_message:{telegram_user_id}"


def set_pending_type(telegram_user_id: int, event_type: str, ttl: int = 3600):
    """Set pending event type in Redis."""
    redis_client.setex(get_pending_type_key(telegram_user_id), ttl, event_type)


def get_pending_type(telegram_user_id: int) -> str | None:
    """Get pending event type from Redis."""
    result = redis_client.get(get_pending_type_key(telegram_user_id))
    return result.decode() if result else None


def clear_pending_type(telegram_user_id: int):
    """Clear pending event type from Redis."""
    redis_client.delete(get_pending_type_key(telegram_user_id))


def save_pending_message(telegram_user_id: int, message_data: dict, ttl: int = 600):
    """Save pending message data in Redis."""
    redis_client.setex(
        get_pending_message_key(telegram_user_id),
        ttl,
        json.dumps(message_data)
    )


def get_pending_message(telegram_user_id: int) -> dict | None:
    """Get pending message data from Redis."""
    result = redis_client.get(get_pending_message_key(telegram_user_id))
    if result:
        return json.loads(result.decode())
    return None


def clear_pending_message(telegram_user_id: int):
    """Clear pending message data from Redis."""
    redis_client.delete(get_pending_message_key(telegram_user_id))


async def get_or_create_user(telegram_user_id: int, session) -> User:
    """Get or create user in database."""
    user = session.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    if not user:
        user = User(telegram_user_id=telegram_user_id)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


async def create_event_from_message(
    message: Message,
    event_type: str,
    source_type: str,
    file_path: Path | None = None,
    s3_key: str | None = None,
    mime_type: str | None = None,
    file_meta: dict | None = None,
    text_content: str | None = None,
) -> Event:
    """Create event record from message."""
    session = get_session().__enter__()
    try:
        user = await get_or_create_user(message.from_user.id, session)
        user_tz = get_user_timezone(user.timezone)
        now_utc = datetime.now(ZoneInfo("UTC"))
        local_date = get_local_date(now_utc, user_tz)

        event = Event(
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            event_type=event_type,
            source_type=source_type,
            created_at_utc=now_utc,
            local_date=local_date,
            raw_file_s3_key=s3_key,
            raw_file_mime=mime_type,
            raw_file_meta=file_meta,
            text_content=text_content,
            processing_status="ok" if text_content else "queued",
        )

        session.add(event)
        session.commit()
        session.refresh(event)

        return event
    finally:
        session.close()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    session = get_session().__enter__()
    try:
        user = await get_or_create_user(message.from_user.id, session)

        welcome_text = (
            "👋 Welcome to <b>Mindforms Diary Bot</b>!\n\n"
            "This bot helps you keep a multimodal diary with:\n"
            "• Text, voice, and photo entries\n"
            "• Automatic transcription and OCR\n"
            "• Daily reminders\n\n"
            "<i>Privacy: Your data is stored securely and only you can access it.</i>\n\n"
            "Use /help to see all commands."
        )

        await message.answer(welcome_text, parse_mode="HTML")
    finally:
        session.close()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = (
        "<b>Available Commands:</b>\n\n"
        "/start - Start using the bot\n"
        "/help - Show this help\n"
        "/reflection - Set next entry as reflection\n"
        "/mindform - Set next entry as mindform\n"
        "/dream - Set next entry as dream\n"
        "/drawing - Set next entry as drawing\n"
        "/face - Set next entry as face photo\n"
        "/timezone [tz] - Show or set timezone (e.g., /timezone Europe/Berlin)\n"
        "/status - Show today's completion status\n"
        "/export_week - Export last 7 days summary\n\n"
        "<b>Usage:</b>\n"
        "✨ <b>Auto-classification:</b> Just send text/photo/voice and the bot will automatically detect the type!\n"
        "📝 Or use commands (/reflection, /dream, etc.) to set the type before sending.\n"
        "🖼️ For photos: Auto-detects handwriting (mindform), face photos, or drawings.\n"
        "💬 For text: Auto-detects reflection, dream, or other types."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("reflection", "mindform", "dream", "drawing", "face"))
async def cmd_set_type(message: Message, command: Command):
    """Handle type-setting commands."""
    event_type = command.command.replace("/", "")
    if event_type == "face":
        event_type = "face_photo"

    set_pending_type(message.from_user.id, event_type)
    await message.answer(
        f"✅ Next entry will be saved as <b>{event_type}</b>.\n"
        f"Send your text, voice, or photo now.",
        parse_mode="HTML",
    )


@router.message(Command("timezone"))
async def cmd_timezone(message: Message):
    """Handle /timezone command."""
    session = get_session().__enter__()
    try:
        user = await get_or_create_user(message.from_user.id, session)
        args = message.text.split(maxsplit=1)

        if len(args) > 1:
            # Set timezone
            new_tz = args[1].strip()
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(new_tz)  # Validate timezone
                user.timezone = new_tz
                session.commit()
                await message.answer(f"✅ Timezone set to <b>{new_tz}</b>", parse_mode="HTML")
            except Exception:
                await message.answer(
                    "❌ Invalid timezone. Use IANA format (e.g., Europe/Berlin, America/New_York)"
                )
        else:
            # Show current timezone
            await message.answer(
                f"Current timezone: <b>{user.timezone}</b>\n\n"
                f"To change: /timezone Europe/Berlin",
                parse_mode="HTML",
            )
    finally:
        session.close()


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Handle /status command."""
    session = get_session().__enter__()
    try:
        user = await get_or_create_user(message.from_user.id, session)
        user_tz = get_user_timezone(user.timezone)
        now_utc = datetime.now(ZoneInfo("UTC"))
        local_date = get_local_date(now_utc, user_tz)

        # Count events for today
        events_today = (
            session.query(Event)
            .filter(
                Event.telegram_user_id == message.from_user.id,
                Event.local_date == local_date,
            )
            .all()
        )

        # Check required types
        status_lines = [f"📊 <b>Status for {local_date}</b>\n"]
        for required_type in user.reminder_required_types:
            has_entry = any(e.event_type == required_type for e in events_today)
            status_lines.append(
                f"{'✅' if has_entry else '❌'} {required_type.capitalize()}"
            )

        status_lines.append(f"\n📝 Total entries today: {len(events_today)}")

        await message.answer("\n".join(status_lines), parse_mode="HTML")
    finally:
        session.close()


@router.message(Command("export_week"))
async def cmd_export_week(message: Message):
    """Handle /export_week command."""
    session = get_session().__enter__()
    try:
        user = await get_or_create_user(message.from_user.id, session)
        user_tz = get_user_timezone(user.timezone)
        now_utc = datetime.now(ZoneInfo("UTC"))
        today = get_local_date(now_utc, user_tz)

        # Get events from last 7 days
        from datetime import timedelta

        start_date = today - timedelta(days=6)

        events = (
            session.query(Event)
            .filter(
                Event.telegram_user_id == message.from_user.id,
                Event.local_date >= start_date,
                Event.local_date <= today,
            )
            .order_by(Event.local_date, Event.created_at_utc)
            .all()
        )

        # Generate markdown summary
        lines = [f"# Mindforms Diary - Week Summary\n"]
        current_date = None
        for event in events:
            if event.local_date != current_date:
                current_date = event.local_date
                lines.append(f"\n## {current_date}\n")

            # Convert UTC time to local time for display
            local_dt = utc_to_local(event.created_at_utc, user_tz)
            time_str = local_dt.strftime("%H:%M")

            lines.append(f"### {event.event_type.capitalize()} ({event.source_type}) - {time_str}")
            if event.text_content:
                lines.append(f"{event.text_content}\n")
            else:
                lines.append("*Processing...*\n")

        summary = "\n".join(lines)
        await message.answer(f"<pre>{summary}</pre>", parse_mode="HTML")
    finally:
        session.close()


@router.callback_query(F.data.startswith("type_"))
async def callback_set_type(callback: CallbackQuery):
    """Handle event type selection from inline keyboard."""
    event_type = callback.data.replace("type_", "")
    if event_type == "other":
        await callback.answer("Please use /dream or /drawing for other types")
        return

    set_pending_type(callback.from_user.id, event_type)
    await callback.answer(f"Type set to {event_type}")

    # Check if there's a pending message to process
    pending_msg = get_pending_message(callback.from_user.id)

    if pending_msg and pending_msg.get("type") == "photo":
        # Process the saved photo
        clear_pending_message(callback.from_user.id)

        await callback.message.edit_text(
            f"✅ Processing as <b>{event_type}</b>...",
            parse_mode="HTML",
        )

        try:
            # Download the photo
            file = await callback.bot.get_file(pending_msg["file_id"])
            file_content = await callback.bot.download_file(file.file_path)
            temp_file = download_file_to_temp(
                f"photo_{pending_msg['file_id']}.jpg", file_content.read()
            )

            # Upload to MinIO and create event
            storage = MinIOClient()
            session = get_session().__enter__()
            try:
                user = await get_or_create_user(callback.from_user.id, session)
                user_tz = get_user_timezone(user.timezone)
                now_utc = datetime.now(ZoneInfo("UTC"))
                local_date = get_local_date(now_utc, user_tz)

                event_id = str(uuid.uuid4())
                s3_key = storage.generate_s3_key(
                    callback.from_user.id, event_id, f"photo_{event_id}.jpg", now_utc
                )
                storage.upload_file(temp_file, s3_key, "image/jpeg")

                # Create a minimal message-like object for create_event_from_message
                class FakeMessage:
                    def __init__(self, user_id, chat_id, message_id):
                        self.from_user = type('obj', (object,), {'id': user_id})()
                        self.chat = type('obj', (object,), {'id': chat_id})()
                        self.message_id = message_id

                fake_msg = FakeMessage(
                    callback.from_user.id,
                    pending_msg["chat_id"],
                    pending_msg["message_id"]
                )

                event = await create_event_from_message(
                    fake_msg,
                    event_type,
                    "photo",
                    s3_key=s3_key,
                    mime_type="image/jpeg",
                    file_meta={
                        "file_id": pending_msg["file_id"],
                        "file_size": pending_msg["file_size"],
                        "width": pending_msg["width"],
                        "height": pending_msg["height"],
                    },
                )

                # Enqueue processing task based on type
                if event_type == "mindform":
                    ocr_handwriting_task.delay(str(event.id))
                    await callback.message.edit_text(
                        f"✅ Photo saved as <b>{event_type}</b>!\n🔄 Extracting text...",
                        parse_mode="HTML",
                    )
                elif event_type == "face_photo":
                    analyze_face_task.delay(str(event.id))
                    await callback.message.edit_text(
                        f"✅ Photo saved as <b>{event_type}</b>!\n🔄 Analyzing face...",
                        parse_mode="HTML",
                    )
                else:
                    await callback.message.edit_text(
                        f"✅ Photo saved as <b>{event_type}</b>!",
                        parse_mode="HTML",
                    )
            finally:
                session.close()

            # Cleanup temp file
            if temp_file.exists():
                temp_file.unlink()
        except Exception as e:
            logger.error(f"Error processing saved photo: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ Error processing photo. Please try sending it again.",
                parse_mode="HTML",
            )
    else:
        # No pending message or not a photo, just confirmation
        if "I think this is" in callback.message.text or "Analyzing" in callback.message.text:
            await callback.message.edit_text(
                f"✅ Confirmed as <b>{event_type}</b>!\n"
                f"Please send your content again to save it.",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                f"✅ Type set to <b>{event_type}</b>. Please send your content now.",
                parse_mode="HTML",
            )


@router.callback_query(F.data.startswith("add_"))
async def callback_add_from_reminder(callback: CallbackQuery):
    """Handle 'Add' button from reminder."""
    event_type = callback.data.replace("add_", "")
    set_pending_type(callback.from_user.id, event_type)
    await callback.answer(f"Type set to {event_type}")
    await callback.message.edit_text(
        f"✅ Type set to <b>{event_type}</b>. Please send your content now.",
        parse_mode="HTML",
    )


@router.message(F.text)
async def handle_text(message: Message):
    """Handle text messages."""
    pending_type = get_pending_type(message.from_user.id)

    if not pending_type:
        # Auto-classify the text
        try:
            await message.answer("🤔 Analyzing content...", parse_mode="HTML")
            gemini = GeminiClient()
            classification = gemini.classify_text_content(message.text)
            pending_type = classification["event_type"]

            # If confidence is low or it's "other", ask for confirmation
            if classification["confidence"] < 0.6 or pending_type == "other":
                await message.answer(
                    f"I think this is a <b>{pending_type}</b> (confidence: {classification['confidence']:.0%}).\n"
                    f"Is this correct?",
                    reply_markup=get_event_type_keyboard(),
                    parse_mode="HTML",
                )
                # Store the auto-detected type so if user confirms, we use it
                set_pending_type(message.from_user.id, pending_type)
                return
        except Exception as e:
            logger.error(f"Error in auto-classification: {e}")
            # Fallback to asking user
            await message.answer(
                "What type of entry is this?",
                reply_markup=get_event_type_keyboard(),
            )
            return

    # Create event
    event = await create_event_from_message(
        message, pending_type, "text", text_content=message.text
    )

    clear_pending_type(message.from_user.id)
    await message.answer(
        f"✅ Saved as <b>{pending_type}</b>!\n\n{message.text}",
        parse_mode="HTML",
    )


@router.message(F.voice)
async def handle_voice(message: Message):
    """Handle voice messages."""
    pending_type = get_pending_type(message.from_user.id)

    if not pending_type:
        # For voice, default to reflection (most common) but allow override
        # We could transcribe first and classify, but that's slower
        # For now, default to reflection
        pending_type = "reflection"
        await message.answer(
            f"🎤 Auto-detected as <b>reflection</b>. If this is wrong, use /dream, /drawing, etc. before sending.",
            parse_mode="HTML",
        )

    try:
        # Download voice file using message's bot
        file = await message.bot.get_file(message.voice.file_id)
        file_content = await message.bot.download_file(file.file_path)

        # Save to temp
        temp_file = download_file_to_temp(
            f"voice_{message.voice.file_id}.ogg", file_content.read()
        )

        # Upload to MinIO
        storage = MinIOClient()
        session = get_session().__enter__()
        try:
            user = await get_or_create_user(message.from_user.id, session)
            user_tz = get_user_timezone(user.timezone)
            now_utc = datetime.now(ZoneInfo("UTC"))
            local_date = get_local_date(now_utc, user_tz)

            event_id = str(uuid.uuid4())
            s3_key = storage.generate_s3_key(
                message.from_user.id, event_id, f"voice_{event_id}.ogg", now_utc
            )
            storage.upload_file(temp_file, s3_key, "audio/ogg")

            # Create event
            event = await create_event_from_message(
                message,
                pending_type,
                "voice",
                s3_key=s3_key,
                mime_type="audio/ogg",
                file_meta={
                    "duration": message.voice.duration,
                    "file_id": message.voice.file_id,
                    "file_size": message.voice.file_size,
                },
            )

            # Enqueue transcription task
            transcribe_audio_task.delay(str(event.id))

            await message.answer(
                f"✅ Voice saved as <b>{pending_type}</b>!\n"
                f"🔄 Transcribing...",
                parse_mode="HTML",
            )
        finally:
            session.close()

        # Cleanup temp file
        if temp_file.exists():
            temp_file.unlink()

    except Exception as e:
        logger.error(f"Error handling voice: {e}", exc_info=True)
        await message.answer("❌ Error processing voice message. Please try again.")


@router.message(F.photo)
async def handle_photo(message: Message):
    """Handle photo messages."""
    pending_type = get_pending_type(message.from_user.id)

    if not pending_type:
        # Auto-classify the image
        try:
            await message.answer("🤔 Analyzing image...", parse_mode="HTML")

            # Get largest photo
            photo: PhotoSize = max(message.photo, key=lambda p: p.file_size)

            # Download photo temporarily for classification
            file = await message.bot.get_file(photo.file_id)
            file_content = await message.bot.download_file(file.file_path)
            temp_file = download_file_to_temp(f"classify_{photo.file_id}.jpg", file_content.read())

            # Auto-rotate if needed
            temp_file = auto_rotate_image(temp_file)

            # Classify
            gemini = GeminiClient()
            classification = gemini.classify_image(temp_file)
            pending_type = classification["event_type"]

            # Cleanup temp file
            if temp_file.exists():
                temp_file.unlink()

            # If confidence is low, ask for confirmation
            if classification["confidence"] < 0.6:
                # Save photo info for later processing
                photo: PhotoSize = max(message.photo, key=lambda p: p.file_size)
                save_pending_message(
                    message.from_user.id,
                    {
                        "type": "photo",
                        "file_id": photo.file_id,
                        "file_size": photo.file_size,
                        "width": photo.width,
                        "height": photo.height,
                        "message_id": message.message_id,
                        "chat_id": message.chat.id,
                    }
                )
                await message.answer(
                    f"I think this is a <b>{pending_type}</b> (confidence: {classification['confidence']:.0%}).\n"
                    f"Is this correct?",
                    reply_markup=get_event_type_keyboard(),
                    parse_mode="HTML",
                )
                set_pending_type(message.from_user.id, pending_type)
                return
        except Exception as e:
            logger.error(f"Error in image auto-classification: {e}")
            # Fallback to asking user
            await message.answer(
                "What type of entry is this?",
                reply_markup=get_event_type_keyboard(),
            )
            return

    try:
        # Get largest photo
        photo: PhotoSize = max(message.photo, key=lambda p: p.file_size)

        # Download photo using message's bot
        file = await message.bot.get_file(photo.file_id)
        file_content = await message.bot.download_file(file.file_path)

        # Save to temp
        temp_file = download_file_to_temp(
            f"photo_{photo.file_id}.jpg", file_content.read()
        )

        # Upload to MinIO
        storage = MinIOClient()
        session = get_session().__enter__()
        try:
            user = await get_or_create_user(message.from_user.id, session)
            user_tz = get_user_timezone(user.timezone)
            now_utc = datetime.now(ZoneInfo("UTC"))
            local_date = get_local_date(now_utc, user_tz)

            event_id = str(uuid.uuid4())
            s3_key = storage.generate_s3_key(
                message.from_user.id, event_id, f"photo_{event_id}.jpg", now_utc
            )
            storage.upload_file(temp_file, s3_key, "image/jpeg")

            # Create event
            event = await create_event_from_message(
                message,
                pending_type,
                "photo",
                s3_key=s3_key,
                mime_type="image/jpeg",
                file_meta={
                    "file_id": photo.file_id,
                    "file_size": photo.file_size,
                    "width": photo.width,
                    "height": photo.height,
                },
            )

            # Enqueue processing task based on type
            if pending_type == "mindform":
                ocr_handwriting_task.delay(str(event.id))
                await message.answer(
                    f"✅ Photo saved as <b>{pending_type}</b>!\n" f"🔄 Extracting text...",
                    parse_mode="HTML",
                )
            elif pending_type == "face_photo":
                analyze_face_task.delay(str(event.id))
                await message.answer(
                    f"✅ Photo saved as <b>{pending_type}</b>!\n" f"🔄 Analyzing face...",
                    parse_mode="HTML",
                )
            else:
                await message.answer(
                    f"✅ Photo saved as <b>{pending_type}</b>!",
                    parse_mode="HTML",
                )
        finally:
            session.close()

        # Cleanup temp file
        if temp_file.exists():
            temp_file.unlink()

    except Exception as e:
        logger.error(f"Error handling photo: {e}", exc_info=True)
        await message.answer("❌ Error processing photo. Please try again.")

