"""Engine/session factory with SQLite pragmas and Alembic bootstrap."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_ENGINES: dict[str, Engine] = {}
_FACTORIES: dict[str, sessionmaker] = {}


def engine() -> Engine:
    url = get_settings().database_url
    if url not in _ENGINES:
        get_settings().database_path.parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"timeout": 30, "check_same_thread": False}, future=True)

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        _ENGINES[url] = eng
        _FACTORIES[url] = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    return _ENGINES[url]


@contextmanager
def session_scope() -> Iterator[Session]:
    engine()
    factory = _FACTORIES[get_settings().database_url]
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def migrate() -> str:
    """Apply Alembic migrations to head (idempotent). Returns the current revision."""
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    base = Path(__file__).resolve().parents[2]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    with engine().begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
    with engine().connect() as connection:
        return MigrationContext.configure(connection).get_current_revision() or "none"


def dispose_all() -> None:
    for eng in _ENGINES.values():
        eng.dispose()
    _ENGINES.clear()
    _FACTORIES.clear()
