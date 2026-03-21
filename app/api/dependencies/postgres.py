# File: app/api/dependencies/postgres.py
"""
===============================================================================
POSTGRESQL FASTAPI DEPENDENCIES
===============================================================================

Provides request-scoped SQLAlchemy sessions.

This layer bridges FastAPI request context with infrastructure adapters.
"""

from __future__ import annotations

from typing import AsyncIterator
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_postgres_session(request: Request) -> AsyncIterator[AsyncSession]:
    """
    Provide request-scoped AsyncSession.

    Session lifecycle:

        open  → dependency start
        close → dependency exit

    Transaction control is handled by UnitOfWork.
    """

    db = request.app.state.db.postgres

    async with db.async_session() as session:
        yield session


__all__ = [
    "get_postgres_session",
]