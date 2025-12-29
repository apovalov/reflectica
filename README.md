# Mindforms Diary Telegram Bot

A multimodal diary Telegram bot that stores text, voice, and photo entries with automatic transcription and OCR using Google Gemini AI.

## Features

- **Multimodal Entries**: Support for text, voice messages, and photos
- **Automatic Processing**:
  - Voice → Speech-to-text transcription
  - Handwritten photos → OCR text extraction
  - Face photos → Emotion and stress analysis
- **Daily Reminders**: Automatic reminders at 23:00 local time for missing required entries
- **Event Types**: Reflection, Mindform, Dream, Drawing, Face Photo
- **Data Storage**: PostgreSQL for metadata, MinIO (S3-compatible) for media files

## Tech Stack

- Python 3.12+
- **Telegram**: aiogram v3
- **Database**: PostgreSQL with SQLAlchemy 2.x
- **Migrations**: Alembic
- **Storage**: MinIO (S3-compatible) via boto3
- **Queue**: Celery + Redis
- **Scheduler**: Celery Beat
- **AI**: Google Gemini API (gemini-2.0-flash-exp for STT, OCR, face analysis)

## Prerequisites

- Docker and Docker Compose
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Gemini API Key (from [Google AI Studio](https://makersuite.google.com/app/apikey))

## Setup Instructions

### 1. Clone and Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your tokens
nano .env
```

Required environment variables:
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
- `GEMINI_API_KEY` - Your Google Gemini API key
- Other variables have defaults but can be customized

### 2. Start Services

```bash
# Start all services (PostgreSQL, Redis, MinIO, Bot, Worker, Beat)
docker compose up -d

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f bot
docker compose logs -f worker
docker compose logs -f beat
```

### 3. Run Database Migrations ⚠️ REQUIRED

**IMPORTANT**: You must run migrations before the bot can work properly!

```bash
# Run migrations (required step!)
docker compose exec bot alembic upgrade head

# Or if alembic is installed locally
alembic upgrade head
```

**Note**: If you see errors like "relation 'users' does not exist", it means migrations haven't been run yet. Run the command above.

### 4. Verify Services

- **PostgreSQL**: `docker compose exec postgres psql -U mindforms -d mindforms`
- **Redis**: `docker compose exec redis redis-cli ping`
- **MinIO**: Access console at http://localhost:9001 (minioadmin/minioadmin)

## Usage

### Bot Commands

- `/start` - Start using the bot and see welcome message
- `/help` - Show all available commands
- `/reflection` - Set next entry as reflection
- `/mindform` - Set next entry as mindform (handwritten photo)
- `/dream` - Set next entry as dream
- `/drawing` - Set next entry as drawing
- `/face` - Set next entry as face photo
- `/timezone [tz]` - Show or set timezone (e.g., `/timezone Europe/Berlin`)
- `/status` - Show today's completion status
- `/export_week` - Export last 7 days summary

### Workflow

1. **Set Entry Type**: Use a command like `/reflection` or `/mindform`
2. **Send Content**: Send text, voice message, or photo
3. **Automatic Processing**:
   - Voice messages are transcribed
   - Mindform photos are OCR'd
   - Face photos are analyzed for emotion
4. **Get Results**: Bot replies with extracted text or analysis

**Alternative**: Just send content without a command, and the bot will ask you to select the type.

### Daily Reminders

The bot automatically sends reminders at 23:00 local time (configurable per user) if required entry types (default: reflection, mindform) are missing for the day.

## Project Structure

```
reflectica/
├── app/
│   ├── bot/              # Telegram bot handlers
│   │   ├── handlers.py   # Message and command handlers
│   │   ├── keyboards.py  # Inline keyboards
│   │   └── main.py       # Bot entry point
│   ├── db/               # Database models and session
│   │   ├── models.py     # SQLAlchemy models
│   │   └── session.py    # Database session management
│   ├── gemini/           # Gemini AI client
│   │   └── client.py     # STT, OCR, face analysis
│   ├── storage/          # MinIO storage client
│   │   └── minio_client.py
│   ├── tasks/            # Celery tasks
│   │   ├── celery_app.py # Celery configuration
│   │   ├── processing.py # Processing tasks
│   │   └── reminders.py  # Reminder tasks
│   ├── scheduler/        # Celery Beat schedule
│   │   └── beat_schedule.py
│   └── utils/            # Utilities
│       ├── timezone.py   # Timezone helpers
│       ├── file_utils.py # File handling
│       └── logging.py    # Logging config
├── alembic/              # Database migrations
│   ├── versions/         # Migration files
│   └── env.py            # Alembic environment
├── docker-compose.yml    # Service orchestration
├── Dockerfile            # Application image
├── pyproject.toml        # Python dependencies
├── alembic.ini           # Alembic configuration
└── README.md             # This file
```

## Development

### Running Locally (without Docker)

1. Install dependencies:
```bash
pip install -e .
```

2. Start services manually:
```bash
# PostgreSQL, Redis, MinIO (or use Docker Compose for these)
docker compose up -d postgres redis minio

# Run migrations
alembic upgrade head

# Run bot
python -m app.bot.main

# Run worker (in another terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Run beat (in another terminal)
celery -A app.tasks.celery_app beat --loglevel=info
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Testing

Test the bot by:
1. Starting all services
2. Finding your bot on Telegram
3. Sending `/start`
4. Testing voice transcription: `/reflection` → send voice message
5. Testing OCR: `/mindform` → send handwritten photo

## Troubleshooting

### Bot not responding
- Check bot logs: `docker compose logs bot`
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Ensure bot is running: `docker compose ps`

### Processing not working
- Check worker logs: `docker compose logs worker`
- Verify `GEMINI_API_KEY` is set and valid
- Check event status in database: `processing_status` field

### Reminders not sending
- Check beat logs: `docker compose logs beat`
- Verify user timezone is set correctly
- Check reminder window (23:00-23:05 local time)

### Database connection issues
- Verify PostgreSQL is running: `docker compose ps postgres`
- Check `POSTGRES_DSN` in `.env`
- Test connection: `docker compose exec postgres psql -U mindforms -d mindforms`

## Environment Variables

See `.env.example` for all available variables. Key ones:

- `TELEGRAM_BOT_TOKEN` - **Required** - Telegram bot token
- `GEMINI_API_KEY` - **Required** - Google Gemini API key
- `POSTGRES_DSN` - Database connection string
- `REDIS_URL` - Redis connection URL
- `S3_ENDPOINT_URL` - MinIO endpoint (default: http://minio:9000)
- `S3_ACCESS_KEY` - MinIO access key
- `S3_SECRET_KEY` - MinIO secret key
- `S3_BUCKET` - Storage bucket name (default: mindforms)
- `DEFAULT_TIMEZONE` - Default user timezone (default: Europe/Berlin)
- `REMINDER_DEFAULT_TIME` - Default reminder time (default: 23:00)

## Security Notes

- Never commit `.env` file (it's in `.gitignore`)
- All data is scoped by `telegram_user_id` for isolation
- Media files stored in MinIO with user-specific paths
- Processing errors are logged but diary content is not logged

## License

This is an MVP implementation. Use at your own risk.

## Support

For issues or questions, check the logs first:
```bash
docker compose logs -f
```

