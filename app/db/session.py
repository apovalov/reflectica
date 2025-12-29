"""Database session management."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

# Get database URL from environment
# Use postgresql+psycopg:// for psycopg v3 (not psycopg2)
raw_dsn = os.environ.get("POSTGRES_DSN", "")
# Keep postgresql+psycopg:// format for psycopg v3
DATABASE_URL = raw_dsn if raw_dsn else ""

# Create sync engine
# Only create engine if DATABASE_URL is provided (lazy initialization)
engine = None

def _get_engine():
    """Lazy initialization of database engine."""
    global engine
    if engine is None:
        if not DATABASE_URL:
            raise ValueError("POSTGRES_DSN environment variable is required")
        engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    return engine

# Create session factory (lazy initialization)
SessionLocal = None

def _get_session_factory():
    """Lazy initialization of session factory."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return SessionLocal


def get_sync_session() -> Session:
    """Get a synchronous database session."""
    return _get_session_factory()()


@contextmanager
def get_session():
    """Context manager for database session."""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initialize database tables (for migrations, not used in production)."""
    Base.metadata.create_all(bind=_get_engine())

