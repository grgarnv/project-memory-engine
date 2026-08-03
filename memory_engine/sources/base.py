"""Source contract and incremental run bookkeeping."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

from memory_engine.ir import Artifact


@dataclass
class SourceRun:
    """What one ingestion pass saw."""
    source_id: str
    produced: int = 0
    skipped: int = 0
    new_watermark: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"{self.source_id}: {self.produced} new, {self.skipped} already seen"
            + (f", watermark -> {self.new_watermark[:16]}" if self.new_watermark else "")
        )


class ArtifactSource(ABC):
    """
    A place artifacts come from.

    `source_id` must be stable across runs - it is the watermark key. Two
    different repositories must not share one, and the same repository must not
    change one between runs, or incremental ingestion silently restarts.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        ...

    @abstractmethod
    def fetch(self, since: str = "") -> Iterator[Artifact]:
        """Artifacts newer than `since`. Oldest first, so watermarks advance."""

    def watermark_for(self, artifact: Artifact) -> str:
        """The cursor value this artifact represents. Default: its timestamp."""
        return artifact.recorded_at
