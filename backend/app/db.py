"""Async database engine, session factory, and dependency."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a session and auto-closes."""
    async with async_session() as session:
        yield session


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[AsyncSession]:
    """Open a session for a write path with commit-on-clean-exit + rollback-on-error.

    Use this instead of bare `async_session()` for write paths so that
    forgetting to commit can't silently drop the work. On exception the
    transaction rolls back before the exception propagates.

    Read-only paths can keep using `async_session()` directly — no commit
    machinery is needed when no writes happen.

    If you need to use post-commit values (e.g. `db.refresh(row)` to pick
    up DB-generated defaults), call `await db.commit()` explicitly inside
    the block; the implicit commit on exit then runs against an empty
    transaction (no-op).
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
