"""Database models for Mindforms Diary Bot."""
import uuid
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User model storing Telegram user preferences."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(
        String(100), default="Europe/Berlin", nullable=False
    )
    reminder_time_local: Mapped[time] = mapped_column(
        Time, default=time(23, 0), nullable=False
    )
    reminder_required_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=["reflection", "mindform"], nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Event(Base):
    """Event model storing diary entries."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # text|voice|photo
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    raw_file_s3_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_file_mime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    raw_file_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False, index=True
    )  # queued|processing|ok|failed
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    derived_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_events_user_date", "telegram_user_id", "local_date"),
        Index("idx_events_user_type_date", "telegram_user_id", "event_type", "local_date"),
    )


class Reminder(Base):
    """Reminder model tracking sent reminders."""

    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="sent", nullable=False
    )  # sent|ack|skipped

    __table_args__ = (
        UniqueConstraint(
            "telegram_user_id", "local_date", "event_type", name="uq_reminder_user_date_type"
        ),
        Index("idx_reminders_user_date", "telegram_user_id", "local_date"),
    )

