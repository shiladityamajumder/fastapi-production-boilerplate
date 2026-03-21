# File: app/api/dependencies/mssql.py
"""
===============================================================================
MSSQL FASTAPI DEPENDENCIES
===============================================================================
"""

from typing import Iterator
from fastapi import Request
from sqlalchemy.orm import Session


def get_mssql_session(request: Request) -> Iterator[Session]:
    """
    Provide synchronous MSSQL session.
    """

    db = request.app.state.db.mssql

    with db.session() as session:
        yield session


__all__ = [
    "get_mssql_session",
]