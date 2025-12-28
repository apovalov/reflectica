"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column('timezone', sa.String(100), nullable=False, server_default='Europe/Berlin'),
        sa.Column('reminder_time_local', sa.Time(), nullable=False, server_default='23:00:00'),
        sa.Column('reminder_required_types', postgresql.ARRAY(sa.String()), nullable=False, server_default='{reflection,mindform}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_telegram_user_id', 'users', ['telegram_user_id'])

    # Create events table
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('source_type', sa.String(20), nullable=False),
        sa.Column('created_at_utc', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('local_date', sa.Date(), nullable=False),
        sa.Column('raw_file_s3_key', sa.Text(), nullable=True),
        sa.Column('raw_file_mime', sa.String(100), nullable=True),
        sa.Column('raw_file_meta', postgresql.JSONB(), nullable=True),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('processing_status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('derived_meta', postgresql.JSONB(), nullable=True),
    )
    op.create_index('ix_events_telegram_user_id', 'events', ['telegram_user_id'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])
    op.create_index('ix_events_local_date', 'events', ['local_date'])
    op.create_index('ix_events_processing_status', 'events', ['processing_status'])
    op.create_index('idx_events_user_date', 'events', ['telegram_user_id', 'local_date'])
    op.create_index('idx_events_user_type_date', 'events', ['telegram_user_id', 'event_type', 'local_date'])

    # Create reminders table
    op.create_table(
        'reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('local_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('sent_at_utc', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('status', sa.String(20), nullable=False, server_default='sent'),
    )
    op.create_index('ix_reminders_telegram_user_id', 'reminders', ['telegram_user_id'])
    op.create_index('idx_reminders_user_date', 'reminders', ['telegram_user_id', 'local_date'])
    op.create_unique_constraint('uq_reminder_user_date_type', 'reminders', ['telegram_user_id', 'local_date', 'event_type'])


def downgrade() -> None:
    op.drop_table('reminders')
    op.drop_table('events')
    op.drop_table('users')

