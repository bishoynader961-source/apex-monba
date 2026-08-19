"""Offline verification that the ORM models compile to valid PostgreSQL DDL (B6).

No live database is required: we render ``CREATE TABLE`` statements for every
model using the PostgreSQL dialect compiler. If any column type or server
default were SQLite-only, this compilation would raise and the test fail,
catching dialect-agnosticism regressions before they reach a real Postgres.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.database import Base


def _compile_all() -> dict[str, str]:
    ddls: dict[str, str] = {}
    for table in Base.metadata.sorted_tables:
        ddls[table.name] = str(
            CreateTable(table).compile(dialect=postgresql.dialect())
        )
    return ddls


def test_all_tables_compile_to_postgres_ddl() -> None:
    ddls = _compile_all()
    assert ddls, "no tables registered on Base.metadata"


def test_key_tables_present_with_b5_columns() -> None:
    ddls = _compile_all()
    for required in ("shifts", "refunds", "audit_logs", "products", "receipts"):
        assert required in ddls, f"missing table {required}"

    audit = ddls["audit_logs"]
    assert "prev_hash" in audit, "audit_logs missing prev_hash column"
    assert "entry_hash" in audit, "audit_logs missing entry_hash column"

    refunds = ddls["refunds"]
    assert "receipt_id" in refunds, "refunds missing receipt_id column"
