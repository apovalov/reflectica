FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for Celery
RUN useradd -m -u 1000 celeryuser

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create temp directory and set ownership
RUN mkdir -p /app/temp && \
    chown -R celeryuser:celeryuser /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER celeryuser

