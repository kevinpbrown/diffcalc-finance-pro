"""Database engine creation and schema/seed initialization.

Centralizes the one-time setup that must run at both first-install (via the
seed script) and at every app startup (via the Splash screen): creating tables
and idempotently seeding configuration rows (Persons, AccountAssetClasses,
PersonalCashFlowProfiles).
"""

from __future__ import annotations

import shutil
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import structlog
from platformdirs import user_data_dir
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger(__name__)

# All ORM models must be imported so SQLAlchemy registers them with Base.metadata
# before create_all() is called.
import personal_finance.domain.balance_sheet  # noqa: E402, F401
import personal_finance.domain.goals  # noqa: E402, F401
from personal_finance.domain import (  # noqa: E402
    AccountAssetClass,
    Base,
    Person,
    PersonalCashFlowProfile,
)
from personal_finance.domain.asset_class import BuiltInAssetClassId  # noqa: E402

_APP_NAME = "diffcalc-finance-pro"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.toml"


def get_db_path() -> Path:
    """Return the platform-specific path for the SQLite database file."""
    return Path(user_data_dir(_APP_NAME)) / "personal_finance.db"


def create_db_engine(db_path: Path | None = None) -> Engine:
    """Create and return a SQLAlchemy engine for the application database.

    Args:
        db_path: Override the database path. Defaults to ``get_db_path()``.

    Returns:
        A connected SQLAlchemy ``Engine``.
    """
    resolved = db_path or get_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{resolved}")


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``.

    Used by ``service/application/`` to open one session per public method
    call (session-per-application-operation), rather than sharing a single
    session for the process lifetime.

    Args:
        engine: The SQLAlchemy engine to bind sessions to.

    Returns:
        A ``sessionmaker`` that produces a fresh ``Session`` on each call.
    """
    return sessionmaker(engine)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open one session, commit on success, roll back and close on exception.

    Scopes a single application-service method call as one unit of work.
    Core-service methods called within the ``with`` block must not call
    ``session.commit()`` themselves — only this context manager commits, so a
    failure partway through a multi-step operation rolls back everything that
    preceded it instead of leaving a partial write.

    Args:
        session_factory: The ``sessionmaker`` to open a session from.

    Yields:
        The opened ``Session``, to be passed into core-service calls.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def backup_database(db_path: Path | None = None) -> None:
    """Copy the live database into the backups directory, retaining 30 copies.

    Safe to call on every startup. If the database does not yet exist (first
    launch) or the copy fails, the function logs a warning and returns without
    raising so startup is never blocked by a backup failure.

    Backups are written to ``<data_dir>/backups/personal_finance_YYYYMMDD_HHMMSS.db``
    and pruned to the 30 most recent after each successful write.

    Args:
        db_path: Override the database path. Defaults to ``get_db_path()``.
    """
    resolved = db_path or get_db_path()
    if not resolved.exists():
        return

    backups_dir = resolved.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"personal_finance_{timestamp}.db"

    try:
        shutil.copy2(resolved, backup_path)
        logger.info("database_backed_up", backup=str(backup_path))
    except Exception:
        logger.warning("database_backup_failed", backup=str(backup_path), exc_info=True)
        return

    existing = sorted(backups_dir.glob("personal_finance_*.db"))
    for old in existing[:-30]:
        try:
            old.unlink()
        except OSError:
            logger.warning("database_backup_prune_failed", path=str(old))


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and return the application TOML configuration.

    Args:
        config_path: Override path to ``config.toml``. Defaults to the
            project-root ``config.toml``.

    Returns:
        Parsed TOML config as a nested ``dict``.

    Raises:
        FileNotFoundError: If ``config_path`` does not exist.
    """
    path = config_path or _CONFIG_PATH
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def initialize_database(engine: Engine, config: dict[str, Any]) -> None:
    """Create all tables and idempotently seed configuration rows.

    Safe to call on every startup; already-present rows are skipped.

    Args:
        engine: The SQLAlchemy engine to initialize.
        config: Parsed TOML config (must contain ``persons.names`` and
            ``asset_classes.names``).
    """
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session, config)


def _seed(session: Session, config: dict[str, Any]) -> None:
    today = date.today()

    existing_names = set(session.scalars(select(Person.name)).all())
    for name in config["persons"]["names"]:
        if name not in existing_names:
            session.add(Person(name=name))
    session.flush()

    persons_without_profile = session.scalars(
        select(Person).where(~Person.id.in_(select(PersonalCashFlowProfile.person_id)))
    ).all()
    for person in persons_without_profile:
        session.add(PersonalCashFlowProfile(person=person))

    # Seed the built-in Cash asset class with its reserved primary key.
    # Cash is never listed in config.toml; it is always seeded here at id=CASH.
    existing_ids = set(session.scalars(select(AccountAssetClass.id)).all())
    if int(BuiltInAssetClassId.CASH) not in existing_ids:
        session.add(
            AccountAssetClass(
                id=int(BuiltInAssetClassId.CASH),
                name="Cash",
                order_precedence=0,
                date_created=today,
            )
        )
    session.flush()

    # Seed TOML-configured asset classes. order_precedence starts at 1 to leave
    # 0 reserved for the built-in Cash class above.
    existing_asset_class_names = set(session.scalars(select(AccountAssetClass.name)).all())
    for order, name in enumerate(config["asset_classes"]["names"], start=1):
        if name not in existing_asset_class_names:
            session.add(AccountAssetClass(name=name, order_precedence=order, date_created=today))

    session.commit()
