"""
File: app/utils/debug.py

Development-only debug print helper.

This utility provides controlled ``print`` output during local development.

Debug output is printed only when:

- ``ENVIRONMENT`` is not ``production``
- ``DEBUG`` is set to ``true``

In production, or whenever debugging is disabled, the function returns without
printing anything.

This helper should be used only for temporary development diagnostics. Do not
pass passwords, tokens, connection strings, patient data, prescriptions, or
other sensitive information.
"""

from __future__ import annotations

from typing import Any

from app.core.config import (
    Environment,
    get_settings,
)
from app.core.logging import sanitize_log_value


def debug(
    message: str,
    **context: Any,
) -> None:
    """
    Print a development-only debug message.

    Args:
        message: Description of the debugging event.
        **context: Optional named values printed with the message.

    Raises:
        ValueError: If the supplied message is blank.

    Example:
        debug(
            "Product request received",
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
    """

    settings = get_settings()

    # Disable all debug prints in production or when DEBUG is false.
    if (
        settings.ENVIRONMENT == Environment.PRODUCTION
        or not settings.DEBUG
    ):
        return

    normalized_message = message.strip()

    if not normalized_message:
        raise ValueError(
            "Debug message must not be blank"
        )

    # Apply the shared redaction logic before printing context values.
    safe_context = sanitize_log_value(context)

    if safe_context:
        print(
            f"[DEBUG] {normalized_message} | {safe_context}",
            flush=True,
        )
        return

    print(
        f"[DEBUG] {normalized_message}",
        flush=True,
    )


__all__ = [
    "debug",
]
