"""SQLite-specific behaviour beyond the shared conformance suite."""
import sqlite3
from pathlib import Path

import pytest

from memory_engine.ingest import Ingestor
from memory_engine.ir import ArtifactType
from memory_engine.store.sqlite import SCHEMA_VERSION, SQLiteProjectMemory
from tests.conftest import make_artifact

DECISION = "## Decision\n\nUse OAuth2 for service-to-service authentication.\n"


def test_schema_version_is_recorded(tmp_path):
    with SQLiteProjectMemory(tmp_path / "m.db") as store:
        row = store.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert row["value"] == str(SCHEMA_VERSION)


def test_memory_survives_close_and_reopen(tmp_path):
    db = tmp_path / "m.db"
    store = SQLiteProjectMemory(db)
    Ingestor(memory=store).ingest(make_artifact(DECISION, ArtifactType.ADR, "2024-01-01"))
    before = store.stats()
    store.close()

    with SQLiteProjectMemory(db) as reopened:
        assert reopened.stats() == before


def test_store_issues_no_update_or_delete():
    """
    Append-only is a property of the schema, not a convention.

    Inspects every SQL string the module can execute. If an UPDATE or DELETE
    turns up here, memory semantics were violated - that is a design failure,
    not a missing store feature.
    """
    import ast
    import inspect

    module = inspect.getmodule(SQLiteProjectMemory)
    tree = ast.parse(Path(inspect.getfile(module)).read_text())

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    literals = [
        node.value.upper()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]

    for sql in literals:
        assert "DELETE FROM" not in sql, sql
        assert "UPDATE " not in sql, sql


def test_reingesting_the_same_file_does_not_grow_memory(tmp_path):
    with SQLiteProjectMemory(tmp_path / "m.db") as store:
        ingestor = Ingestor(memory=store)
        artifact = make_artifact(DECISION, ArtifactType.ADR, "2024-01-01")
        ingestor.ingest(artifact)
        before = store.stats()
        ingestor.ingest(artifact)
        assert store.stats() == before
