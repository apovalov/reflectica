#!/bin/bash
# Run database migrations

docker compose exec bot alembic upgrade head

