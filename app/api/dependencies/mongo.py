# File: app/api/dependencies/mongo.py
"""
===============================================================================
MONGO FASTAPI DEPENDENCIES
===============================================================================
"""

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase


async def get_mongo_db(request: Request) -> AsyncIOMotorDatabase:
    """
    Provide Mongo database handle.

    No transaction management.
    """
    return request.app.state.db.mongo.db


__all__ = [
    "get_mongo_db",
]