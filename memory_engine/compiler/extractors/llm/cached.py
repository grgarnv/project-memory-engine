"""
Cached LLM extraction.

An LLM extractor breaks the compiler's central promise unless it is pinned and
cached. RFC 004 §3 states the amended invariant: compilation is deterministic
given `(content, compiler version, ontology version, extractor configuration)`.
A model call satisfies none of that by itself - same input, different day,
different output, and every downstream fact silently changes provenance.

This wrapper makes it hold:

  - Every extraction is keyed on the full tuple: segment text, model, prompt
    version, temperature, and provider name. Two runs with the same tuple return
    the same statements because the second one never calls the model.
  - The cache is content-addressed and durable, so re-compiling a ten-year
    archive costs nothing after the first pass. This is also what makes an LLM
    extractor affordable at all - a real repository is millions of segments, and
    paying per segment per run is not a strategy.
  - Changing the model or the prompt changes the key. Old entries are not
    invalidated and not deleted: they remain the record of what was extracted
    under the old configuration, which is what lets a fact compiled in 2026
    still be explained in 2034.

The last point is the one that matters architecturally. A model upgrade is a NEW
compilation, not a correction of the old one. Memory already knows how to hold
two assertions from different sources - that is the evidence model - so an
upgrade lands as additional evidence rather than as a rewrite.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from memory_engine.compiler.extractors.base import StatementExtractor
from memory_engine.compiler.extractors.llm.providers import (
    LLMProvider,
    LLMStatementExtractor,
    MockLLMProvider,
)
from memory_engine.ir import Segment, Statement

# Bump when the prompt text changes. It is part of the cache key, so forgetting
# to bump it serves stale extractions under a new prompt - the one failure mode
# that would be invisible.
PROMPT_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS extractions (
    key         TEXT PRIMARY KEY,
    statements  TEXT NOT NULL,
    model       TEXT NOT NULL,
    prompt_ver  TEXT NOT NULL,
    temperature REAL NOT NULL
);
"""


class ExtractionCache:
    """Durable, content-addressed store of past extractions."""

    def __init__(self, path: str | Path = ".pme-extraction-cache.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(text: str, model: str, prompt_version: str, temperature: float,
            provider: str) -> str:
        payload = json.dumps(
            [text, model, prompt_version, temperature, provider], sort_keys=True
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> list[dict] | None:
        row = self.conn.execute(
            "SELECT statements FROM extractions WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(row["statements"])

    def put(self, key: str, statements: list[dict], model: str,
            prompt_version: str, temperature: float) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO extractions "
            "(key, statements, model, prompt_ver, temperature) VALUES (?, ?, ?, ?, ?)",
            (key, json.dumps(statements), model, prompt_version, temperature),
        )
        self.conn.commit()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def close(self) -> None:
        self.conn.close()


class CachedLLMStatementExtractor(StatementExtractor):
    """
    An LLM extractor that keeps compilation reproducible.

    Wraps any `LLMProvider`. The pinned configuration is exposed as
    `fingerprint` so a `CompiledArtifact` can record which extractor produced it
    - without that, a stored compilation cannot be identified with the tuple it
    came from, and RFC 004 §3 is unenforceable.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        cache: ExtractionCache | None = None,
        model: str = "",
        temperature: float = 0.0,
        prompt_version: str = PROMPT_VERSION,
    ):
        self.provider = provider or MockLLMProvider()
        self.cache = cache or ExtractionCache(":memory:")
        self.temperature = temperature
        self.prompt_version = prompt_version
        self.model = model or getattr(self.provider, "model", type(self.provider).__name__)
        self._inner = LLMStatementExtractor(provider=self.provider)

    @property
    def fingerprint(self) -> dict[str, str | float]:
        """The configuration compilation is reproducible *given*."""
        return {
            "extractor": "CachedLLMStatementExtractor",
            "provider": type(self.provider).__name__,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "temperature": self.temperature,
        }

    def extract(self, segment: Segment) -> list[Statement]:
        key = ExtractionCache.key(
            segment.text, self.model, self.prompt_version,
            self.temperature, type(self.provider).__name__,
        )

        cached = self.cache.get(key)
        if cached is not None:
            return [
                Statement(subject=s["subject"], predicate=s["predicate"],
                          target=s["target"], observation_id=segment.observation_id)
                for s in cached
            ]

        statements = self._inner.extract(segment)
        self.cache.put(
            key,
            [{"subject": s.subject, "predicate": s.predicate, "target": s.target}
             for s in statements],
            self.model, self.prompt_version, self.temperature,
        )
        return statements
