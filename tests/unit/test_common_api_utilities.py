"""Tests for shared API filtering, sorting, pagination, and response contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.common.exceptions import ValidationError
from app.common.filters import apply_dynamic_filters, apply_prefix_search
from app.common.pagination import (
    PaginationParams,
    apply_pagination,
    build_pagination_meta,
)
from app.common.response import APIResponse, APIResponseModel
from app.common.sorting import SortOrder, apply_sorting
from app.modules.auth.models import User, UserRole
from app.modules.auth.repository import AuthRepository


def test_pagination_rejects_invalid_bounds_and_builds_metadata() -> None:
    params = PaginationParams(limit=20, offset=20)
    metadata = build_pagination_meta(total_count=45, params=params)

    assert metadata.has_next is True
    assert metadata.limit == 20
    assert metadata.offset == 20
    with pytest.raises(ValueError):
        PaginationParams(limit=0)


def test_pagination_helper_applies_limit_and_offset() -> None:
    statement = apply_pagination(
        select(User),
        params=PaginationParams(limit=5, offset=10),
    )

    assert statement._limit_clause.value == 5
    assert statement._offset_clause.value == 10


def test_shared_filters_and_sorting_are_allow_list_based() -> None:
    statement = apply_dynamic_filters(
        select(User),
        filters={"role": UserRole.USER, "is_active": False},
        allowed_filters={"role": User.role, "is_active": User.is_active},
        boolean_fields={"is_active"},
    )
    statement = apply_prefix_search(
        statement,
        search="person%",
        columns=(User.email, User.username),
        max_length=100,
    )
    statement = apply_sorting(
        statement,
        sort_by="email",
        sort_order=SortOrder.DESC,
        allowed_fields={"email": User.email},
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "ILIKE" in compiled
    assert "users.is_active" in compiled
    assert "users.role" in compiled
    assert "users.email DESC" in compiled
    with pytest.raises(ValidationError, match="Unsupported sort field"):
        apply_sorting(
            select(User),
            sort_by="password_hash",
            allowed_fields={"email": User.email},
        )


@pytest.mark.asyncio
async def test_admin_user_listing_uses_shared_query_utilities() -> None:
    scalar_result = Mock()
    scalar_result.all.return_value = []
    session = Mock()
    session.scalar = AsyncMock(return_value=3)
    session.scalars = AsyncMock(return_value=scalar_result)
    repository = AuthRepository(session)

    users, total = await repository.list_users(
        search="person",
        role=UserRole.USER,
        is_active=False,
        limit=5,
        offset=10,
        sort_by="email",
        sort_order=SortOrder.ASC,
    )
    count_statement = session.scalar.await_args.args[0]
    data_statement = session.scalars.await_args.args[0]
    compiled = str(data_statement.compile(dialect=postgresql.dialect()))

    assert users == []
    assert total == 3
    assert "ILIKE" in compiled
    assert "users.is_active IS false" in compiled
    assert "users.role" in compiled
    assert "users.email ASC" in compiled
    assert "LIMIT" in compiled and "OFFSET" in compiled
    assert "ILIKE" in str(count_statement.compile(dialect=postgresql.dialect()))


def test_success_response_envelope_matches_openapi_model() -> None:
    response = APIResponse.success(message="Loaded", data={"count": 1})
    body = APIResponseModel[dict[str, int]].model_validate_json(response.body)

    assert body.success is True
    assert body.data == {"count": 1}
    assert body.error is None
