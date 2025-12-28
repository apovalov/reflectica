"""Celery Beat schedule configuration."""
from celery.schedules import crontab

from app.tasks.celery_app import celery_app

# Schedule reminder task to run every 5 minutes
celery_app.conf.beat_schedule = {
    "send-due-reminders": {
        "task": "send_due_reminders",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
}

