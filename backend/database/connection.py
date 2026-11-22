"""
backend/database/connection.py
Database Connection Manager and Session Factory for WorkspaceAI.
Supports SQLite (Local-First Zero-Config default) and optional MySQL.
"""
from __future__ import annotations

import logging
from typing import Generator, Optional, Any

from backend.core.config import settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_engine():
    """
    Returns or lazily initializes the singleton SQLAlchemy Engine.
    Defaults to SQLite ('sqlite:///workspace_ai.db') for zero-config local run.
    """
    global _engine
    if _engine is not None:
        return _engine

    try:
        from sqlalchemy import create_engine, event
        from sqlalchemy.engine import Engine
    except ImportError as exc:
        raise RuntimeError(
            "SQLAlchemy is required to manage database connections. "
            "Please run: pip install sqlalchemy"
        ) from exc

    db_url = settings.db_url
    logger.info("Initializing Database connection engine with URL: %s", db_url)

    if "sqlite" in db_url:
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},  # Required for SQLite multi-threading
            echo=False,
        )

        # Enforce SQLite foreign key constraints
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # MySQL Connection with connection pooling
        _engine = create_engine(
            db_url,
            pool_size=settings.mysql_pool_size,
            max_overflow=20,
            pool_recycle=settings.mysql_pool_recycle,
            pool_pre_ping=True,
            echo=False,
        )

    return _engine


def get_session_factory():
    """Returns or lazily creates the sessionmaker factory bound to the active engine."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    try:
        from sqlalchemy.orm import sessionmaker
    except ImportError as exc:
        raise RuntimeError(
            "SQLAlchemy is required to manage database sessions. "
            "Please run: pip install sqlalchemy"
        ) from exc

    engine = get_engine()
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _session_factory


def get_db() -> Generator[Any, None, None]:
    """
    FastAPI dependency and standard context manager for database sessions.
    Automatically handles commit and rollback on exception.
    """
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    """
    Pings the database with 'SELECT 1' to verify connection health.
    Returns True if healthy, False otherwise.
    """
    try:
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as err:
        logger.warning("Database connection check failed: %s", err)
        return False


# Backward-compatible alias
check_mysql_connection = check_db_connection
