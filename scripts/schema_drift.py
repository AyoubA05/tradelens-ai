"""Compare two databases' schemas, structurally, and classify the differences.

Purpose: decide whether the production-derived schema is genuinely equivalent
to what Alembic revision r8s9t0u1v2w3 produces. That question has to be
answered with evidence before anything is stamped, because `alembic stamp`
asserts "the schema is already at this revision" — if that assertion is wrong,
every later migration builds on a false premise and the failure surfaces
somewhere far away from the cause.

Usage:
    REFERENCE_URL="<empty db migrated to r8s9t0u1v2w3>" \
    TARGET_URL="<dev branch copied from production>" \
    python -m scripts.schema_drift

The reference database must be built by running migrations from scratch on the
same engine as the target — comparing Postgres against SQLite would report
dozens of meaningless type differences and bury the real ones.

Exit code is 0 when the only differences are classified benign, 1 otherwise,
so this can gate a pipeline.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Tuple

from sqlalchemy import create_engine, inspect

# Differences that are environment noise rather than drift.
#
# Alembic's own bookkeeping table is expected to differ: the whole reason this
# script exists is that the target does not have it.
_IGNORED_TABLES = {"alembic_version"}

# Serial/identity implementation details render differently across Postgres
# versions and between create_all and migration paths without meaning anything.
_BENIGN_DEFAULT_PREFIXES = ("nextval(",)


def _normalise_type(type_) -> str:
    """A comparable rendering of a column type.

    Deliberately lossy on length for VARCHAR: `String` and `String(64)` are the
    same storage in Postgres, and create_all vs ALTER paths disagree about
    whether a length was ever declared. Length differences are reported as
    benign rather than hidden, via _classify.
    """
    return str(type_).upper().strip()


def _column_facts(inspector, table: str) -> Dict[str, Dict[str, Any]]:
    facts = {}
    for column in inspector.get_columns(table):
        facts[column["name"]] = {
            "type": _normalise_type(column["type"]),
            "nullable": bool(column["nullable"]),
            "default": column.get("default"),
        }
    return facts


def _index_facts(inspector, table: str) -> Dict[str, Dict[str, Any]]:
    facts = {}
    for index in inspector.get_indexes(table):
        facts[index["name"]] = {
            "columns": tuple(index.get("column_names") or ()),
            "unique": bool(index.get("unique")),
        }
    # Unique *constraints* and unique *indexes* are interchangeable in Postgres
    # for our purposes, so fold them into one namespace or a constraint on one
    # side and an index on the other reads as drift when it is not.
    for constraint in inspector.get_unique_constraints(table):
        name = (
            constraint.get("name")
            or f"uq_{table}_{'_'.join(constraint['column_names'])}"
        )
        facts.setdefault(
            name,
            {"columns": tuple(constraint.get("column_names") or ()), "unique": True},
        )
    return facts


def _fk_facts(inspector, table: str) -> set:
    return {
        (
            tuple(fk.get("constrained_columns") or ()),
            fk.get("referred_table"),
            tuple(fk.get("referred_columns") or ()),
        )
        for fk in inspector.get_foreign_keys(table)
    }


def _pk_facts(inspector, table: str) -> tuple:
    return tuple(inspector.get_pk_constraint(table).get("constrained_columns") or ())


def _classify(kind: str, detail: str) -> str:
    """BENIGN or DRIFT. Anything uncertain is DRIFT — that is the safe default."""
    if kind == "column_type":
        # VARCHAR vs VARCHAR(n): same storage, different declaration path.
        if "VARCHAR" in detail and "TEXT" not in detail:
            return "BENIGN"
    if kind == "column_default" and any(
        prefix in detail for prefix in _BENIGN_DEFAULT_PREFIXES
    ):
        return "BENIGN"
    return "DRIFT"


def compare(reference_url: str, target_url: str) -> Tuple[List[str], List[str]]:
    """Return (benign, drift) difference descriptions."""
    ref = inspect(create_engine(reference_url))
    tgt = inspect(create_engine(target_url))

    benign: List[str] = []
    drift: List[str] = []

    def record(kind: str, message: str) -> None:
        (benign if _classify(kind, message) == "BENIGN" else drift).append(message)

    ref_tables = set(ref.get_table_names()) - _IGNORED_TABLES
    tgt_tables = set(tgt.get_table_names()) - _IGNORED_TABLES

    for table in sorted(ref_tables - tgt_tables):
        drift.append(f"TABLE missing from target: {table}")
    for table in sorted(tgt_tables - ref_tables):
        drift.append(f"TABLE only in target: {table}")

    for table in sorted(ref_tables & tgt_tables):
        ref_cols = _column_facts(ref, table)
        tgt_cols = _column_facts(tgt, table)

        for name in sorted(set(ref_cols) - set(tgt_cols)):
            drift.append(f"COLUMN missing from target: {table}.{name}")
        for name in sorted(set(tgt_cols) - set(ref_cols)):
            drift.append(f"COLUMN only in target: {table}.{name}")

        for name in sorted(set(ref_cols) & set(tgt_cols)):
            r, t = ref_cols[name], tgt_cols[name]
            if r["type"] != t["type"]:
                record(
                    "column_type",
                    f"TYPE {table}.{name}: reference={r['type']} target={t['type']}",
                )
            if r["nullable"] != t["nullable"]:
                drift.append(
                    f"NULLABLE {table}.{name}: reference={r['nullable']} "
                    f"target={t['nullable']}"
                )
            if r["default"] != t["default"]:
                record(
                    "column_default",
                    f"DEFAULT {table}.{name}: reference={r['default']} "
                    f"target={t['default']}",
                )

        if _pk_facts(ref, table) != _pk_facts(tgt, table):
            drift.append(
                f"PRIMARY KEY {table}: reference={_pk_facts(ref, table)} "
                f"target={_pk_facts(tgt, table)}"
            )

        ref_fks, tgt_fks = _fk_facts(ref, table), _fk_facts(tgt, table)
        for fk in sorted(ref_fks - tgt_fks):
            drift.append(f"FOREIGN KEY missing from target: {table} {fk}")
        for fk in sorted(tgt_fks - ref_fks):
            drift.append(f"FOREIGN KEY only in target: {table} {fk}")

        ref_ix, tgt_ix = _index_facts(ref, table), _index_facts(tgt, table)
        for name in sorted(set(ref_ix) - set(tgt_ix)):
            drift.append(
                f"INDEX missing from target: {table}.{name} "
                f"{ref_ix[name]['columns']} unique={ref_ix[name]['unique']}"
            )
        for name in sorted(set(tgt_ix) - set(ref_ix)):
            drift.append(f"INDEX only in target: {table}.{name}")
        for name in sorted(set(ref_ix) & set(tgt_ix)):
            if ref_ix[name]["unique"] != tgt_ix[name]["unique"]:
                drift.append(
                    f"UNIQUENESS {table}.{name}: reference={ref_ix[name]['unique']} "
                    f"target={tgt_ix[name]['unique']}"
                )

    return benign, drift


def main() -> int:
    reference_url = os.getenv("REFERENCE_URL")
    target_url = os.getenv("TARGET_URL")
    if not reference_url or not target_url:
        print("Set REFERENCE_URL and TARGET_URL.", file=sys.stderr)
        return 2

    benign, drift = compare(reference_url, target_url)

    print("=" * 70)
    print("SCHEMA DRIFT REPORT")
    print("=" * 70)
    print()
    print(f"A. Benign / environment differences ({len(benign)})")
    for line in benign or ["  none"]:
        print(f"  {line}")
    print()
    print(f"B. Genuine drift requiring reconciliation ({len(drift)})")
    for line in drift or ["  none"]:
        print(f"  {line}")
    print()
    if drift:
        print("VERDICT: schema is NOT equivalent to the reference revision.")
        print("Do not stamp. Reconcile category B first, then re-run.")
        return 1
    print("VERDICT: schema is equivalent to the reference revision.")
    print("Stamping is justified by evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
