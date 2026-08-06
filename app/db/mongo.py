# """
# File: app/db/mongo.py

# Asynchronous MongoDB client lifecycle adapter using PyMongo Async.

# MongoDB is an optional integration. When disabled, no client or connection pool
# is created.

# One ``MongoDatabase`` instance is created per FastAPI or Celery worker process.
# Repositories should reuse the shared database proxy instead of constructing
# independent clients.
# """

# from __future__ import annotations

# from typing import Any

# from pymongo import AsyncMongoClient, ReadPreference
# from pymongo.asynchronous.database import AsyncDatabase
# from pymongo.write_concern import WriteConcern

# from app.core.config import AppSettings
# from app.core.logging import get_logger


# logger = get_logger(__name__)


# type Document = dict[str, Any]


# _READ_PREFERENCES = {
#     "primary": ReadPreference.PRIMARY,
#     "primaryPreferred": ReadPreference.PRIMARY_PREFERRED,
#     "secondary": ReadPreference.SECONDARY,
#     "secondaryPreferred": ReadPreference.SECONDARY_PREFERRED,
#     "nearest": ReadPreference.NEAREST,
# }


# class MongoDatabase:
#     """
#     Own one process-local asynchronous MongoDB client and database proxy.
#     """

#     def __init__(
#         self,
#         *,
#         uri: str,
#         database_name: str,
#         settings: AppSettings,
#     ) -> None:
#         """
#         Initialize the MongoDB client and configured database proxy.

#         Args:
#             uri: Validated MongoDB connection URI.
#             database_name: Logical MongoDB database used by repositories.
#             settings: Validated application settings.

#         Raises:
#             ValueError: If the URI, database name, read preference, or write
#                 concern is invalid.
#         """

#         normalized_uri = uri.strip()
#         normalized_database_name = database_name.strip()

#         if not normalized_uri:
#             raise ValueError(
#                 "MongoDB URI must not be blank"
#             )

#         if not normalized_database_name:
#             raise ValueError(
#                 "MongoDB database name must not be blank"
#             )

#         read_preference = _READ_PREFERENCES.get(
#             settings.MONGO_READ_PREFERENCE
#         )

#         if read_preference is None:
#             raise ValueError(
#                 "Unsupported MongoDB read preference"
#             )

#         write_concern_value: str | int

#         if settings.MONGO_WRITE_CONCERN == "1":
#             write_concern_value = 1
#         elif settings.MONGO_WRITE_CONCERN == "majority":
#             write_concern_value = "majority"
#         else:
#             raise ValueError(
#                 "Unsupported MongoDB write concern"
#             )

#         self._client: AsyncMongoClient[Document] = AsyncMongoClient(
#             normalized_uri,
#             appname=settings.PROJECT_NAME,
#             minPoolSize=settings.MONGO_MIN_POOL_SIZE,
#             maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
#             serverSelectionTimeoutMS=(
#                 settings.MONGO_SERVER_SELECTION_TIMEOUT_MS
#             ),
#             connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
#             socketTimeoutMS=settings.MONGO_SOCKET_TIMEOUT_MS,
#             retryReads=True,
#             retryWrites=settings.MONGO_RETRY_WRITES,
#             uuidRepresentation="standard",
#         )

#         self._database: AsyncDatabase[Document] = (
#             self._client.get_database(
#                 normalized_database_name,
#                 read_preference=read_preference,
#                 write_concern=WriteConcern(
#                     w=write_concern_value,
#                 ),
#             )
#         )

#         self._database_name = normalized_database_name

#         logger.info(
#             "MongoDB database adapter initialized",
#             extra={
#                 "database": normalized_database_name,
#                 "min_pool_size": settings.MONGO_MIN_POOL_SIZE,
#                 "max_pool_size": settings.MONGO_MAX_POOL_SIZE,
#                 "read_preference": settings.MONGO_READ_PREFERENCE,
#                 "write_concern": settings.MONGO_WRITE_CONCERN,
#             },
#         )

#     @classmethod
#     def from_settings(
#         cls,
#         settings: AppSettings,
#     ) -> MongoDatabase:
#         """
#         Build the adapter from validated application settings.

#         Args:
#             settings: Validated application settings.

#         Returns:
#             Initialized MongoDB adapter.

#         Raises:
#             RuntimeError: If MongoDB is disabled or incompletely configured.
#         """

#         if not settings.ENABLE_MONGO:
#             raise RuntimeError(
#                 "MongoDB is not enabled"
#             )

#         uri = settings.mongo_uri_value
#         database_name = settings.MONGO_DB_NAME

#         if not uri:
#             raise RuntimeError(
#                 "MongoDB URI is not configured"
#             )

#         if not database_name:
#             raise RuntimeError(
#                 "MongoDB database name is not configured"
#             )

#         return cls(
#             uri=uri,
#             database_name=database_name,
#             settings=settings,
#         )

#     @property
#     def client(
#         self,
#     ) -> AsyncMongoClient[Document]:
#         """
#         Return the process-local asynchronous MongoDB client.

#         Direct client access is intended for infrastructure operations such as
#         sessions, transactions, and administrative commands.
#         """

#         return self._client

#     @property
#     def database(
#         self,
#     ) -> AsyncDatabase[Document]:
#         """
#         Return the configured MongoDB database proxy.
#         """

#         return self._database

#     @property
#     def database_name(self) -> str:
#         """
#         Return the configured logical MongoDB database name.
#         """

#         return self._database_name

#     async def ping(self) -> None:
#         """
#         Verify MongoDB server selection and command execution.

#         The PyMongo client connects lazily, so this command performs the
#         startup connectivity validation.

#         Raises:
#             Exception: Propagates connectivity, authentication, timeout, and
#                 server-selection failures.
#         """

#         await self._client.admin.command(
#             "ping"
#         )

#         logger.debug(
#             "MongoDB connectivity verified"
#         )

#     async def close(self) -> None:
#         """
#         Close the MongoDB client and all owned connection pools.
#         """

#         await self._client.close()

#         logger.info(
#             "MongoDB database adapter closed"
#         )


# __all__ = [
#     "Document",
#     "MongoDatabase",
# ]
