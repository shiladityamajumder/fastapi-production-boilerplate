"""File: app/worker/__init__.py.

Optional background-worker package.

Celery background processing is currently disabled. Importing this package does
not initialize Celery, connect to a broker, register worker signals, create
threads, or initialize database resources.

The reusable worker implementation is retained as fully commented reference
code inside this package. Activation instructions are included in each file.
"""

__all__: list[str] = []
