"""Policy and lock invariants for administrative operations."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.auth.repository import AuthRepository


@pytest.mark.asyncio
async def test_bootstrap_and_admin_mutations_share_transaction_lock() -> None:
    session = Mock()
    session.execute = AsyncMock()
    repository = AuthRepository(session)

    await repository.lock_admin_mutations()
    await repository.lock_first_admin_bootstrap()

    queries = [str(call.args[0]) for call in session.execute.await_args_list]
    assert queries == [
        "SELECT pg_advisory_xact_lock(613470922)",
        "SELECT pg_advisory_xact_lock(613470922)",
    ]
