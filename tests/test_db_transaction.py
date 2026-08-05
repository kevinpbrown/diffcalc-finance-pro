"""Regression tests for db.transaction() — the fix for the shared-session
transaction-safety bug described in
specs/working-artefacts/adr/2026-07-28-backend-shared-session-transaction-safety.md.

Before this fix, a single SQLAlchemy Session was held for the entire app
process. A failed commit() left it needing rollback() (PendingRollbackError on
any further use) with nothing ever calling rollback() — one failed operation
poisoned every subsequent operation, on every screen, until restart.

Under session-per-application-operation, each call opens its own session via
db.transaction(), which rolls back and closes on any exception. These tests
confirm that behavior directly: a failing unit of work is rolled back cleanly,
and — sharing the same underlying connection via StaticPool, the same way a
single-file SQLite database is shared across sessions in the real app — a
subsequent, unrelated unit of work succeeds without any special recovery step.
"""

from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from personal_finance.db import transaction
from personal_finance.domain.asset_class import AccountAssetClass
from personal_finance.domain.base import Base


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)


def test_failed_commit_rolls_back_and_does_not_poison_later_operations(
    session_factory: sessionmaker[Session],
) -> None:
    # First unit of work: insert two AccountAssetClass rows sharing the same
    # explicit primary key, forcing an IntegrityError at commit time — this is
    # the exact class of failure (a commit() that raises) that used to leave
    # the shared session permanently unusable.
    with pytest.raises(IntegrityError):
        with transaction(session_factory) as session:
            session.add(
                AccountAssetClass(
                    id=1, name="Equity", order_precedence=1, date_created=date(2024, 1, 1)
                )
            )
            session.add(
                AccountAssetClass(
                    id=1, name="Duplicate", order_precedence=2, date_created=date(2024, 1, 1)
                )
            )

    # Second, unrelated unit of work against the same session factory (same
    # underlying connection): must succeed with no special recovery step. Under
    # the old architecture this would have raised PendingRollbackError.
    with transaction(session_factory) as session:
        session.add(
            AccountAssetClass(
                id=1, name="Equity", order_precedence=1, date_created=date(2024, 1, 1)
            )
        )

    with transaction(session_factory) as session:
        result = session.query(AccountAssetClass).filter_by(id=1).one()
        assert result.name == "Equity"


def test_successful_transaction_commits(session_factory: sessionmaker[Session]) -> None:
    with transaction(session_factory) as session:
        session.add(
            AccountAssetClass(
                name="Fixed Income", order_precedence=1, date_created=date(2024, 1, 1)
            )
        )

    with transaction(session_factory) as session:
        assert session.query(AccountAssetClass).filter_by(name="Fixed Income").count() == 1


def test_non_db_exception_also_rolls_back(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(ValueError, match="boom"):
        with transaction(session_factory) as session:
            session.add(
                AccountAssetClass(
                    name="Never Committed", order_precedence=1, date_created=date(2024, 1, 1)
                )
            )
            raise ValueError("boom")

    with transaction(session_factory) as session:
        assert session.query(AccountAssetClass).filter_by(name="Never Committed").count() == 0
