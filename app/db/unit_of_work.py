# File: app/db/unit_of_work.py
"""
===============================================================================
ASYNC UNIT OF WORK (STRICT TRANSACTION BOUNDARY)
===============================================================================

Provides deterministic transaction management for SQLAlchemy AsyncSession.

The Unit of Work pattern ensures that a single business operation is executed
inside a single, controlled transaction.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This component belongs to the Infrastructure Layer.

It provides a strict transaction boundary between the service layer
and the database layer.

Responsibilities:

    • Start transaction
    • Ensure exactly one commit OR rollback
    • Guarantee deterministic transaction lifecycle
    • Prevent nested transaction ambiguity

This module is NOT responsible for:

    • business logic
    • repository logic
    • HTTP request handling
    • dependency injection

-------------------------------------------------------------------------------
TRANSACTION MODEL
-------------------------------------------------------------------------------

Usage pattern:

    async with UnitOfWork(session):

        repo = ProductRepository(uow.session)

        await repo.create(...)

Transaction behavior:

    Success
        → commit

    Exception
        → rollback

-------------------------------------------------------------------------------
RESTRICTIONS
-------------------------------------------------------------------------------

Repositories:

    ✔ may call session.flush()
    ✘ must NOT call commit()
    ✘ must NOT call rollback()

Services:

    ✔ must control transaction scope using UnitOfWork

Routes:

    ✘ must NOT manage transactions directly

-------------------------------------------------------------------------------
DESIGN GOALS
-------------------------------------------------------------------------------

The UnitOfWork enforces the following guarantees:

    • One business operation = one transaction
    • No partial writes
    • Explicit transaction boundaries
    • Exception-safe behavior
"""

from __future__ import annotations

from typing import Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# UNIT OF WORK
# =============================================================================


class UnitOfWork:
    """
    Strict Async Unit of Work for SQLAlchemy 2.0.

    This class manages transaction lifecycle for a request-scoped
    AsyncSession.

    It ensures that database operations executed inside the context
    are committed atomically.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize UnitOfWork with an existing AsyncSession.

        The session is typically provided by the FastAPI dependency layer.

        Args:
            session:
                Active SQLAlchemy AsyncSession bound to the request.

        Invariants:

            • session must be open
            • session must not already be inside a transaction
        """

        self._session: AsyncSession = session
        self._transaction_started: bool = False

    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------

    @property
    def session(self) -> AsyncSession:
        """
        Expose the underlying AsyncSession.

        This session is passed to repositories that execute database queries.
        """
        return self._session

    # -------------------------------------------------------------------------
    # CONTEXT MANAGER ENTRY
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> "UnitOfWork":
        """
        Begin transaction boundary.

        Raises:
            RuntimeError if the session already has an active transaction.
        """

        if self._session.in_transaction():
            raise RuntimeError(
                "Cannot start UnitOfWork: session already in transaction"
            )

        await self._session.begin()

        self._transaction_started = True

        return self

    # -------------------------------------------------------------------------
    # CONTEXT MANAGER EXIT
    # -------------------------------------------------------------------------

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb,
    ) -> None:
        """
        Complete transaction lifecycle.

        Behavior:

            No exception
                → commit

            Exception occurred
                → rollback

        Guarantees:

            • exactly one commit OR rollback
            • deterministic transaction completion
            • no transaction leaks
        """

        if not self._transaction_started:
            return

        try:

            if exc_type is None:

                if self._session.in_transaction():
                    await self._session.commit()

            else:

                if self._session.in_transaction():
                    await self._session.rollback()

        finally:

            self._transaction_started = False

    # -------------------------------------------------------------------------
    # MANUAL TRANSACTION CONTROL (ADVANCED USE)
    # -------------------------------------------------------------------------

    async def commit(self) -> None:
        """
        Manually commit the active transaction.

        This method should be used only for advanced workflows where
        multiple commit points are required.

        Raises:
            RuntimeError if UnitOfWork is not active.
        """

        if not self._transaction_started:
            raise RuntimeError("UnitOfWork not active")

        if not self._session.in_transaction():
            raise RuntimeError("No active transaction to commit")

        await self._session.commit()

    async def rollback(self) -> None:
        """
        Manually rollback the active transaction.

        Intended for advanced error handling flows.
        """

        if not self._transaction_started:
            raise RuntimeError("UnitOfWork not active")

        if not self._session.in_transaction():
            raise RuntimeError("No active transaction to rollback")

        await self._session.rollback()

    # -------------------------------------------------------------------------
    # DEBUGGING SUPPORT
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        """
        Provide helpful debug representation.
        """

        return (
            f"<UnitOfWork session_id={id(self._session)} "
            f"active={self._transaction_started}>"
        )
