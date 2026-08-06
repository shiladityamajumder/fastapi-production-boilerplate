"""File: app/db/uow.py.

SQLAlchemy asynchronous Unit of Work.

A Unit of Work owns exactly one ``AsyncSession`` and one transaction. It is
created for a single request operation or Celery task and must never be shared
between concurrent executions.

Typical usage:

    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        repository = ProductRepository(uow.session)
        await repository.create(...)

The context manager commits when the block succeeds, rolls back when an
exception escapes, and always closes the session.
"""

from __future__ import annotations

from time import perf_counter
from types import TracebackType  # noqa: TC003
from typing import Any, Self

from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002
    AsyncSessionTransaction,  # noqa: TC002
    async_sessionmaker,  # noqa: TC002
)

from app.core.logging import get_logger

logger = get_logger(__name__)


class SQLAlchemyUnitOfWork:
    """Own one asynchronous SQLAlchemy session and transaction.

    The Unit of Work is intended primarily for write workflows requiring an
    explicit transaction boundary. Repositories receive ``uow.session`` only
    after the context manager has been entered.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        database_name: str = "relational",
    ) -> None:
        """Initialize a Unit of Work.

        Args:
            session_factory: Process-local SQLAlchemy async session factory.
            database_name: Safe logical database name used in logs.

        Raises:
            ValueError: If ``database_name`` is blank.
        """
        normalized_database_name = database_name.strip()

        if not normalized_database_name:
            raise ValueError("database_name must not be blank")

        self._session_factory = session_factory
        self._database_name = normalized_database_name

        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._started_at: float | None = None

    @property
    def session(self) -> AsyncSession:
        """Return the active SQLAlchemy session.

        Returns:
            Session owned by this Unit of Work.

        Raises:
            RuntimeError: If the Unit of Work has not been entered or has
                already been closed.
        """
        if self._session is None:
            raise RuntimeError(
                "The unit of work is not active. "
                "Enter it before accessing the session."
            )

        return self._session

    @property
    def is_active(self) -> bool:
        """Return whether this Unit of Work owns an active transaction."""
        return (
            self._session is not None
            and self._transaction is not None
            and self._transaction.is_active
        )

    async def __aenter__(self) -> Self:
        """Create a session and begin one explicit transaction.

        Returns:
            Active Unit of Work.

        Raises:
            RuntimeError: If the same instance is entered more than once.
            Exception: If session or transaction initialization fails.
        """
        await self.begin()

        return self

    async def begin(self) -> None:
        """Create the owned session and begin its transaction.

        Raises:
            RuntimeError: If this instance is already active.
            Exception: If SQLAlchemy cannot start the transaction.
        """
        if self._session is not None:
            raise RuntimeError(
                "This unit of work has already been entered"
            )

        session = self._session_factory()
        self._session = session

        try:
            self._transaction = await session.begin()
            self._started_at = perf_counter()
        except Exception:
            await self._close_session()
            raise

        logger.debug(
            "Database transaction started",
            extra={
                "database": self._database_name,
            },
        )

    async def commit(self) -> None:
        """Commit the active transaction.

        When commit fails, a rollback is attempted before the original commit
        error is re-raised.

        Raises:
            RuntimeError: If no transaction is active.
            Exception: If commit fails.
        """
        transaction = self._require_transaction()

        try:
            await transaction.commit()

            logger.debug(
                "Database transaction committed",
                extra={
                    "database": self._database_name,
                    "duration_ms": self._duration_ms(),
                },
            )
        except Exception:
            logger.exception(
                "Database transaction commit failed",
                extra={
                    "database": self._database_name,
                    "duration_ms": self._duration_ms(),
                },
            )

            try:
                if self._session is not None:
                    await self._session.rollback()
            except Exception:
                logger.exception(
                    "Rollback after commit failure also failed",
                    extra={
                        "database": self._database_name,
                    },
                )

            raise
        finally:
            self._clear_transaction_state()

    async def rollback(self) -> None:
        """Roll back the active transaction.

        Raises:
            RuntimeError: If no transaction is active.
            Exception: If rollback fails.
        """
        transaction = self._require_transaction()

        try:
            await transaction.rollback()

            logger.debug(
                "Database transaction rolled back",
                extra={
                    "database": self._database_name,
                    "duration_ms": self._duration_ms(),
                },
            )
        except Exception:
            logger.exception(
                "Database transaction rollback failed",
                extra={
                    "database": self._database_name,
                    "duration_ms": self._duration_ms(),
                },
            )
            raise
        finally:
            self._clear_transaction_state()

    async def flush(self) -> None:
        """Flush pending ORM changes without committing the transaction.

        Raises:
            RuntimeError: If no transaction is active.
        """
        self._require_transaction()

        await self.session.flush()

    async def refresh(
        self,
        instance: Any,
        *,
        attribute_names: list[str] | None = None,
    ) -> None:
        """Refresh an ORM instance inside the active transaction.

        Args:
            instance: SQLAlchemy ORM instance.
            attribute_names: Optional attributes to refresh.

        Raises:
            RuntimeError: If no transaction is active.
        """
        self._require_transaction()

        await self.session.refresh(
            instance,
            attribute_names=attribute_names,
        )

    async def close(self) -> None:
        """Roll back active work and close the owned session.

        This method is safe to call more than once. A rollback failure is
        logged, but session closure is still attempted.
        """
        if self.is_active:
            try:
                await self.rollback()
            except Exception:
                logger.exception(
                    "Rollback failed while closing unit of work",
                    extra={
                        "database": self._database_name,
                    },
                )

        await self._close_session()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit successful work, roll back failed work, and close the session.

        An exception raised inside the context remains the primary exception.
        A rollback or close failure is logged without replacing it.

        Args:
            exc_type: Escaping exception type.
            exc: Escaping exception instance.
            traceback: Escaping exception traceback.
        """
        _ = exc_type, traceback

        try:
            if self.is_active:
                if exc is None:
                    await self.commit()
                else:
                    try:
                        await self.rollback()
                    except Exception:
                        logger.exception(
                            "Rollback failed while another exception "
                            "was already active",
                            extra={
                                "database": self._database_name,
                                "original_exception_type": type(exc).__name__,
                            },
                        )
        finally:
            try:
                await self._close_session()
            except Exception:
                if exc is not None:
                    logger.exception(
                        "Session close failed while another exception "
                        "was already active",
                        extra={
                            "database": self._database_name,
                            "original_exception_type": type(exc).__name__,
                        },
                    )
                else:
                    raise

    def _require_transaction(self) -> AsyncSessionTransaction:
        """Return the active transaction.

        Returns:
            Active SQLAlchemy asynchronous transaction.

        Raises:
            RuntimeError: If no transaction is active.
        """
        if (
            self._transaction is None
            or not self._transaction.is_active
        ):
            raise RuntimeError(
                "No unit-of-work transaction is active"
            )

        return self._transaction

    def _duration_ms(self) -> float | None:
        """Return elapsed transaction time in milliseconds."""
        if self._started_at is None:
            return None

        return round(
            (perf_counter() - self._started_at) * 1_000,
            2,
        )

    def _clear_transaction_state(self) -> None:
        """Clear transaction-specific internal state."""
        self._transaction = None
        self._started_at = None

    async def _close_session(self) -> None:
        """Close and clear the owned SQLAlchemy session."""
        session = self._session

        self._session = None
        self._clear_transaction_state()

        if session is not None:
            await session.close()


# Concise public name used by application services and dependencies.
UnitOfWork = SQLAlchemyUnitOfWork


__all__ = [
    "SQLAlchemyUnitOfWork",
    "UnitOfWork",
]
