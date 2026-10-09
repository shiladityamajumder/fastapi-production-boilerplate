"""Migration metadata and revision discovery for auth and stored files."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.base import Base
from app.modules.auth import models as auth_models  # noqa: F401


def test_auth_models_are_in_shared_metadata_and_revision_is_discoverable() -> None:
    expected_tables = {
        "users",
        "auth_refresh_sessions",
        "auth_one_time_tokens",
        "auth_otp_challenges",
        "auth_rate_limits",
        "stored_files",
        "audit_logs",
        "notification_outbox",
    }
    assert expected_tables <= set(Base.metadata.tables)

    repository_root = Path(__file__).resolve().parents[2]
    directory = ScriptDirectory.from_config(Config(repository_root / "alembic.ini"))
    revisions = tuple(directory.walk_revisions())
    assert len(revisions) == 4
    assert revisions[0].revision == "20261009_04"
    assert revisions[0].down_revision == "20261009_03"
    assert revisions[1].revision == "20261009_03"
    assert revisions[1].down_revision == "20261009_02"
    assert revisions[2].revision == "20261009_02"
    assert revisions[2].down_revision == "20261009_01"
    assert revisions[3].revision == "20261009_01"
    assert revisions[3].down_revision is None
