# File: app/api/dependencies/uow.py
"""
===============================================================================
SQL UNIT OF WORK DEPENDENCY
===============================================================================

Provides a UnitOfWork instance for whichever SQL database
is enabled in the infrastructure registry.
"""

from typing import AsyncIterator

from fastapi import Request

from app.db.unit_of_work import UnitOfWork


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    """
    Provide SQL UnitOfWork using configured database.

    Supports:
        - PostgreSQL
        - MySQL
        - MSSQL
    """

    registry = request.app.state.db

    db = registry.postgres or registry.mysql or registry.mssql

    if db is None:
        raise RuntimeError("No SQL database configured")

    async with db.async_session() as session:
        yield UnitOfWork(session)
        await session.close()


__all__ = [
    "get_uow",
]