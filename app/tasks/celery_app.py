"""Celery application configuration."""
import os

from celery import Celery

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "mindforms",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    broker_connection_retry_on_startup=True,  # Fix deprecation warning
)

# Import tasks and beat schedule after celery_app is created
# With lazy database initialization, imports are safe even if DB isn't ready yet
from app.tasks import processing, reminders  # noqa: F401
from app.scheduler import beat_schedule  # noqa: F401

