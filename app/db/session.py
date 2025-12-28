"""Database session management."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

# Get database URL from environment
# Support both postgresql+psycopg:// and postgresql:// formats
raw_dsn = os.environ.get("POSTGRES_DSN", "")
DATABASE_URL = raw_dsn.replace("postgresql+psycopg://", "postgresql://") if raw_dsn else ""

# Create sync engine
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_sync_session() -> Session:
    """Get a synchronous database session."""
    return SessionLocal()


@contextmanager
def get_session():
    """Context manager for database session."""
    session = SessionLocal()
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
    Base.metadata.create_all(bind=engine)

