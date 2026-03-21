# File: app/api/dependencies/mysql.py
"""
===============================================================================
MYSQL FASTAPI DEPENDENCIES
===============================================================================
"""

from typing import Iterator
from fastapi import Request
from sqlalchemy.orm import Session


def get_mysql_session(request: Request) -> Iterator[Session]:
    """
    Provide synchronous MySQL session.

    Must be executed inside threadpool if used in async routes.
    """

    db = request.app.state.db.mysql

    with db.session() as session:
        yield session


__all__ = [
    "get_mysql_session",
]