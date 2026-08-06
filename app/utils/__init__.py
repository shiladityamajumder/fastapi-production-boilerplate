"""File: app/utils/__init__.py.

Small framework-independent utility functions.

Utilities in this package must be:

- stateless,
- broadly reusable,
- independent of FastAPI and database sessions,
- free from infrastructure initialization,
- focused enough to justify their own module.

Feature-specific helpers should remain inside their owning feature module.
"""

__all__: list[str] = []
