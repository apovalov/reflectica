"""Celery tasks for processing events."""
import asyncio
import uuid
from pathlib import Path
from typing import Any

from app.bot.entry_summary import send_entry_summary
from app.db.models import Event
from app.db.session import get_session
from app.gemini.client import GeminiClient
from app.storage.minio_client import MinIOClient
from app.tasks.celery_app import celery_app
from app.utils.file_utils import auto_rotate_image, download_file_to_temp
from app.utils.logging import logger


@celery_app.task(name="transcribe_audio")
def transcribe_audio_task(event_id: str):
    """Transcribe audio event using Gemini."""
    session = None
    temp_file = None
    try:
        session = get_session().__enter__()
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()

        if not event:
            logger.error(f"Event {event_id} not found")
            return

        if event.processing_status != "queued":
            logger.warning(f"Event {event_id} is not in queued status")
            return

        # Update status to processing
        event.processing_status = "processing"
        session.commit()

        # Download file from MinIO
        storage = MinIOClient()
        temp_file = Path(f"/app/temp/temp_{event_id}")
        storage.download_file(event.raw_file_s3_key, temp_file)

        # Transcribe using Gemini
        gemini = GeminiClient()
        result = gemini.transcribe_audio(temp_file, event.raw_file_mime or "audio/ogg")

        # Update event
        transcription_text = result.get("text", "")
        classification_result = None
        if transcription_text.strip():
            try:
                classification_result = gemini.classify_text_content(transcription_text)
                new_type = classification_result.get("event_type")
                if new_type:
                    event.event_type = new_type
            except Exception as exc:
                logger.error(
                    "Error classifying transcribed text for %s: %s",
                    event_id,
                    exc,
                    exc_info=True,
                )

        derived_meta: dict[str, Any] = {
            "language": result.get("language"),
            "segments": result.get("segments", []),
        }
        if classification_result:
            derived_meta["classification"] = classification_result

        event.text_content = transcription_text
        event.derived_meta = derived_meta
        event.processing_status = "ok"
        session.commit()

        logger.info(f"Successfully transcribed event {event_id}")
        try:
            asyncio.run(send_entry_summary(str(event.id)))
        except Exception as exc:
            logger.error("Failed to send entry summary for %s: %s", event_id, exc)

    except Exception as e:
        logger.error(f"Error processing audio event {event_id}: {e}", exc_info=True)
        if session:
            try:
                event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()
                if event:
                    event.processing_status = "failed"
                    event.processing_error = str(e)
                    session.commit()
            except Exception:
                pass
    finally:
        if temp_file and temp_file.exists():
            temp_file.unlink()
        if session:
            session.close()


@celery_app.task(name="ocr_handwriting")
def ocr_handwriting_task(event_id: str):
    """OCR handwriting from image event using Gemini."""
    session = None
    temp_file = None
    try:
        session = get_session().__enter__()
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()

        if not event:
            logger.error(f"Event {event_id} not found")
            return

        if event.processing_status != "queued":
            logger.warning(f"Event {event_id} is not in queued status")
            return

        # Update status to processing
        event.processing_status = "processing"
        session.commit()

        # Download file from MinIO
        storage = MinIOClient()
        temp_file = Path(f"/app/temp/temp_{event_id}")
        storage.download_file(event.raw_file_s3_key, temp_file)

        # Auto-rotate image if needed
        temp_file = auto_rotate_image(temp_file)

        # OCR using Gemini
        gemini = GeminiClient()
        result = gemini.ocr_handwriting(temp_file)

        # Update event
        event.text_content = result.get("cleaned_text", "")
        event.derived_meta = {
            "raw_text": result.get("raw_text", ""),
            "cleaned_text": result.get("cleaned_text", ""),
            "language": result.get("language"),
            "confidence": result.get("confidence"),
            "notes": result.get("notes"),
        }
        event.processing_status = "ok"
        session.commit()

        logger.info(f"Successfully OCR'd event {event_id}")
        try:
            asyncio.run(send_entry_summary(str(event.id)))
        except Exception as exc:
            logger.error("Failed to send entry summary for %s: %s", event_id, exc)

    except Exception as e:
        logger.error(f"Error processing OCR event {event_id}: {e}", exc_info=True)
        if session:
            try:
                event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()
                if event:
                    event.processing_status = "failed"
                    event.processing_error = str(e)
                    session.commit()
            except Exception:
                pass
    finally:
        if temp_file and temp_file.exists():
            temp_file.unlink()
        if session:
            session.close()


@celery_app.task(name="analyze_face")
def analyze_face_task(event_id: str):
    """Analyze face emotion from image event using Gemini."""
    session = None
    temp_file = None
    try:
        session = get_session().__enter__()
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()

        if not event:
            logger.error(f"Event {event_id} not found")
            return

        if event.processing_status != "queued":
            logger.warning(f"Event {event_id} is not in queued status")
            return

        # Update status to processing
        event.processing_status = "processing"
        session.commit()

        # Download file from MinIO
        storage = MinIOClient()
        temp_file = Path(f"/app/temp/temp_{event_id}")
        storage.download_file(event.raw_file_s3_key, temp_file)

        # Auto-rotate image if needed
        temp_file = auto_rotate_image(temp_file)

        # Analyze face using Gemini
        gemini = GeminiClient()
        result = gemini.analyze_face(temp_file)

        # Create human-readable text summary
        emotion = result.get("dominant_emotion", "unknown")
        stress = result.get("stress_level_0_10", 5)
        confidence = result.get("confidence", 0.0)
        notes = result.get("notes", "")

        text_summary = f"Emotion: {emotion}\nStress level: {stress}/10\nConfidence: {confidence:.0%}"
        if notes:
            text_summary += f"\nNotes: {notes}"

        # Update event
        event.text_content = text_summary
        event.derived_meta = {
            "dominant_emotion": emotion,
            "stress_level_0_10": stress,
            "confidence": confidence,
            "notes": notes,
        }
        event.processing_status = "ok"
        session.commit()

        logger.info(f"Successfully analyzed face for event {event_id}")
        try:
            asyncio.run(send_entry_summary(str(event.id)))
        except Exception as exc:
            logger.error("Failed to send entry summary for %s: %s", event_id, exc)

    except Exception as e:
        logger.error(f"Error processing face analysis event {event_id}: {e}", exc_info=True)
        if session:
            try:
                event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).first()
                if event:
                    event.processing_status = "failed"
                    event.processing_error = str(e)
                    session.commit()
            except Exception:
                pass
    finally:
        if temp_file and temp_file.exists():
            temp_file.unlink()
        if session:
            session.close()
