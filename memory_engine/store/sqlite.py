"""
SQLite persistence engine.

Same contracts as the in-memory store, same conformance suite. Schema mirrors
the model exactly - one table per type, no ORM, no migration framework yet.

The schema is append-only by construction: there is no UPDATE and no DELETE
anywhere in this file. Supersession is a row in `supersessions`, never a change
to a fact. If a future change needs an UPDATE statement here, that is a signal
the memory semantics were violated, not that the store needs a new feature.

Idempotency: every insert is INSERT OR IGNORE against a content-addressed
primary key, so replaying the same delta twice is a no-op rather than a
duplicate. That matters for the same reason ordering does - ingestion should
converge, not accumulate artefacts of how it was run.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from memory_engine.memory.contracts import ProjectMemory
from memory_engine.memory.model import (
    ARTIFACT_REF_PREFIX,
    ConflictEdge,
    EvidenceRecord,
    GlobalEntityBinding,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
)
from memory_engine.ontology import EntityType, Predicate

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id             TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    aliases        TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias     TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id          TEXT PRIMARY KEY,
    subject_ref TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object_ref  TEXT NOT NULL,
    fact_type   TEXT NOT NULL DEFAULT 'observation'
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_ref);
CREATE INDEX IF NOT EXISTS idx_facts_object  ON facts(object_ref);

CREATE TABLE IF NOT EXISTS evidence (
    id                    TEXT PRIMARY KEY,
    persisted_fact_id     TEXT NOT NULL,
    source_artifact_id    TEXT NOT NULL,
    source_fact_id        TEXT NOT NULL,
    artifact_type         TEXT NOT NULL DEFAULT 'document',
    recorded_at           TEXT NOT NULL DEFAULT '',
    confidence            REAL NOT NULL DEFAULT 1.0,
    authority             REAL NOT NULL DEFAULT 0.5,
    supporting_statements TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_evidence_fact ON evidence(persisted_fact_id);

CREATE TABLE IF NOT EXISTS supersessions (
    superseding_fact_id TEXT NOT NULL,
    superseded_fact_id  TEXT NOT NULL,
    reason              TEXT NOT NULL DEFAULT '',
    source_artifact_id  TEXT NOT NULL DEFAULT '',
    recorded_at         TEXT NOT NULL DEFAULT '',
    basis               TEXT NOT NULL DEFAULT 'ingestion_order',
    PRIMARY KEY (superseding_fact_id, superseded_fact_id)
);
CREATE INDEX IF NOT EXISTS idx_sup_retired ON supersessions(superseded_fact_id);

CREATE TABLE IF NOT EXISTS conflicts (
    fact_a_id          TEXT NOT NULL,
    fact_b_id          TEXT NOT NULL,
    conflict_type      TEXT NOT NULL DEFAULT 'contradictory_assertion',
    source_artifact_id TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (fact_a_id, fact_b_id, conflict_type)
);

CREATE TABLE IF NOT EXISTS applied_artifacts (
    artifact_id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL DEFAULT ''
);
"""


def _fact(row: sqlite3.Row) -> PersistedFact:
    return PersistedFact(
        id=row["id"],
        subject_ref=row["subject_ref"],
        predicate=Predicate(row["predicate"]),
        object_ref=row["object_ref"],
        fact_type=row["fact_type"],
    )


def _evidence(row: sqlite3.Row) -> EvidenceRecord:
    return EvidenceRecord(
        id=row["id"],
        persisted_fact_id=row["persisted_fact_id"],
        source_artifact_id=row["source_artifact_id"],
        source_fact_id=row["source_fact_id"],
        artifact_type=row["artifact_type"],
        recorded_at=row["recorded_at"],
        confidence=row["confidence"],
        authority=row["authority"],
        supporting_statements=json.loads(row["supporting_statements"]),
    )


def _supersession(row: sqlite3.Row) -> SupersessionEdge:
    return SupersessionEdge(
        superseding_fact_id=row["superseding_fact_id"],
        superseded_fact_id=row["superseded_fact_id"],
        reason=row["reason"],
        source_artifact_id=row["source_artifact_id"],
        recorded_at=row["recorded_at"],
        basis=row["basis"],
    )


def _conflict(row: sqlite3.Row) -> ConflictEdge:
    return ConflictEdge(
        fact_a_id=row["fact_a_id"],
        fact_b_id=row["fact_b_id"],
        conflict_type=row["conflict_type"],
        source_artifact_id=row["source_artifact_id"],
    )


class SQLiteProjectMemory(ProjectMemory):
    """Durable store. Pass ":memory:" for an ephemeral one."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SQLiteProjectMemory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- MemoryReader -------------------------------------------------------

    def find_entity_by_canonical_name(self, canonical_name: str) -> str | None:
        key = canonical_name.strip().lower()
        row = self.conn.execute(
            "SELECT id FROM entities WHERE LOWER(canonical_name) = ?", (key,)
        ).fetchone()
        if row:
            return row["id"]
        row = self.conn.execute(
            "SELECT entity_id FROM entity_aliases WHERE alias = ?", (key,)
        ).fetchone()
        return row["entity_id"] if row else None

    def get_persisted_fact_by_id(self, fact_id: str) -> PersistedFact | None:
        row = self.conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return _fact(row) if row else None

    def find_existing_fact(
        self, subject_ref: str, predicate: Predicate, object_ref: str
    ) -> PersistedFact | None:
        row = self.conn.execute(
            "SELECT * FROM facts WHERE subject_ref = ? AND predicate = ? AND object_ref = ?",
            (subject_ref, predicate.value, object_ref),
        ).fetchone()
        return _fact(row) if row else None

    def get_active_facts_for_subject(self, subject_ref: str) -> list[PersistedFact]:
        rows = self.conn.execute(
            """
            SELECT * FROM facts
            WHERE subject_ref = ?
              AND id NOT IN (SELECT superseded_fact_id FROM supersessions)
            """,
            (subject_ref,),
        ).fetchall()
        return [_fact(r) for r in rows]

    def get_active_facts_with_object(
        self, object_ref: str, predicates: tuple[Predicate, ...] | None = None
    ) -> list[PersistedFact]:
        sql = """
            SELECT * FROM facts
            WHERE object_ref = ?
              AND id NOT IN (SELECT superseded_fact_id FROM supersessions)
        """
        params: list[str] = [object_ref]
        if predicates:
            placeholders = ",".join("?" for _ in predicates)
            sql += f" AND predicate IN ({placeholders})"
            params.extend(p.value for p in predicates)
        return [_fact(r) for r in self.conn.execute(sql, params).fetchall()]

    def latest_evidence_time(self, fact_id: str) -> str:
        row = self.conn.execute(
            "SELECT MAX(recorded_at) AS t FROM evidence "
            "WHERE persisted_fact_id = ? AND recorded_at != ''",
            (fact_id,),
        ).fetchone()
        return row["t"] or "" if row else ""

    # -- BeliefReader -------------------------------------------------------

    def facts_mentioning(self, ref: str) -> list[PersistedFact]:
        rows = self.conn.execute(
            "SELECT * FROM facts WHERE subject_ref = ? OR object_ref = ?", (ref, ref)
        ).fetchall()
        return [_fact(r) for r in rows]

    def get_fact(self, fact_id: str) -> PersistedFact | None:
        return self.get_persisted_fact_by_id(fact_id)

    def evidence_for_fact(self, fact_id: str) -> list[EvidenceRecord]:
        rows = self.conn.execute(
            "SELECT * FROM evidence WHERE persisted_fact_id = ? ORDER BY recorded_at, id",
            (fact_id,),
        ).fetchall()
        return [_evidence(r) for r in rows]

    def supersession_edges_retiring(self, fact_id: str) -> list[SupersessionEdge]:
        rows = self.conn.execute(
            "SELECT * FROM supersessions WHERE superseded_fact_id = ?", (fact_id,)
        ).fetchall()
        return [_supersession(r) for r in rows]

    def supersession_edges_caused_by(self, fact_id: str) -> list[SupersessionEdge]:
        rows = self.conn.execute(
            "SELECT * FROM supersessions WHERE superseding_fact_id = ?", (fact_id,)
        ).fetchall()
        return [_supersession(r) for r in rows]

    def is_superseded(self, fact_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM supersessions WHERE superseded_fact_id = ? LIMIT 1", (fact_id,)
        ).fetchone()
        return row is not None

    def conflicts_involving(self, fact_id: str) -> list[ConflictEdge]:
        rows = self.conn.execute(
            "SELECT * FROM conflicts WHERE fact_a_id = ? OR fact_b_id = ?",
            (fact_id, fact_id),
        ).fetchall()
        return [_conflict(r) for r in rows]

    def resolve_ref(self, name: str) -> str | None:
        return self.find_entity_by_canonical_name(name)

    def label_for_ref(self, ref: str) -> str:
        row = self.conn.execute(
            "SELECT canonical_name FROM entities WHERE id = ?", (ref,)
        ).fetchone()
        if row:
            return row["canonical_name"]
        if ref.startswith(ARTIFACT_REF_PREFIX):
            return f"<{ref[len(ARTIFACT_REF_PREFIX):][:12]}>"
        return ref

    # -- MemoryWriter -------------------------------------------------------

    def apply_delta(self, delta: MemoryDelta) -> None:
        cur = self.conn.cursor()

        for binding in delta.bound_entities:
            cur.execute(
                "INSERT OR IGNORE INTO entities (id, canonical_name, entity_type, aliases) "
                "VALUES (?, ?, ?, ?)",
                (
                    binding.global_entity_id,
                    binding.local_canonical_name,
                    binding.entity_type.value,
                    json.dumps(binding.aliases),
                ),
            )
            for alias in [binding.local_canonical_name, *binding.aliases]:
                cur.execute(
                    "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
                    (alias.strip().lower(), binding.global_entity_id),
                )

        for fact in delta.promoted_facts:
            cur.execute(
                "INSERT OR IGNORE INTO facts (id, subject_ref, predicate, object_ref, fact_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (fact.id, fact.subject_ref, fact.predicate.value, fact.object_ref, fact.fact_type),
            )

        for ev in delta.evidence_records:
            cur.execute(
                "INSERT OR IGNORE INTO evidence "
                "(id, persisted_fact_id, source_artifact_id, source_fact_id, artifact_type, "
                " recorded_at, confidence, authority, supporting_statements) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ev.id, ev.persisted_fact_id, ev.source_artifact_id, ev.source_fact_id,
                    ev.artifact_type, ev.recorded_at, ev.confidence, ev.authority,
                    json.dumps(ev.supporting_statements),
                ),
            )

        for edge in delta.supersessions:
            cur.execute(
                "INSERT OR IGNORE INTO supersessions "
                "(superseding_fact_id, superseded_fact_id, reason, source_artifact_id, "
                " recorded_at, basis) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    edge.superseding_fact_id, edge.superseded_fact_id, edge.reason,
                    edge.source_artifact_id, edge.recorded_at, edge.basis,
                ),
            )

        for c in delta.conflicts:
            cur.execute(
                "INSERT OR IGNORE INTO conflicts "
                "(fact_a_id, fact_b_id, conflict_type, source_artifact_id) VALUES (?, ?, ?, ?)",
                (c.fact_a_id, c.fact_b_id, c.conflict_type, c.source_artifact_id),
            )

        cur.execute(
            "INSERT OR IGNORE INTO applied_artifacts (artifact_id, recorded_at) VALUES (?, ?)",
            (delta.artifact_id, delta.artifact_recorded_at),
        )
        self.conn.commit()

    # -- diagnostics --------------------------------------------------------

    def stats(self) -> dict[str, int]:
        def count(table: str) -> int:
            return self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]

        facts = count("facts")
        superseded = self.conn.execute(
            "SELECT COUNT(DISTINCT superseded_fact_id) AS c FROM supersessions"
        ).fetchone()["c"]
        return {
            "entities": count("entities"),
            "facts": facts,
            "active_facts": facts - superseded,
            "evidence": count("evidence"),
            "supersessions": count("supersessions"),
            "conflicts": count("conflicts"),
            "artifacts": count("applied_artifacts"),
        }
