"""
Ingestion.

The only module that touches the compiler, the linker, and a store at once.
Everything else stays on one side of the boundary. Keeping the wiring here is
what lets `tests/test_import_boundaries.py` assert that the compiler never
imports the linker and the resolver never imports either.

    load_artifact()  file -> Artifact (with identity and timestamp)
    ingest()         Artifact -> compiled -> delta -> applied
    ingest_scenario() a directory of artifacts, in manifest order
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from memory_engine.compiler import MemoryCompiler
from memory_engine.ir import Artifact, ArtifactType, CompiledArtifact, deterministic_id
from memory_engine.linker import ThreePassMemoryPatchLinker
from memory_engine.memory.contracts import ProjectMemory
from memory_engine.memory.model import MemoryDelta

MANIFEST_NAME = "manifest.json"

# Filename hints, checked in order. Only a convenience for loose files - a
# scenario manifest always wins.
_TYPE_HINTS: tuple[tuple[str, ArtifactType], ...] = (
    ("adr", ArtifactType.ADR),
    ("rfc", ArtifactType.DOCUMENT),
    ("pr", ArtifactType.PR),
    ("commit", ArtifactType.COMMIT),
    ("issue", ArtifactType.ISSUE),
)


def infer_artifact_type(path: Path) -> ArtifactType:
    name = path.stem.lower()
    for hint, atype in _TYPE_HINTS:
        if name.startswith(hint) or f"_{hint}" in name or f"-{hint}" in name:
            return atype
    return ArtifactType.DOCUMENT


def load_artifact(
    path: str | Path,
    artifact_type: ArtifactType | None = None,
    recorded_at: str = "",
) -> Artifact:
    """
    Read a file into an Artifact.

    Identity is content-addressed: the same bytes at the same type always
    produce the same artifact ID, so re-ingesting a file is idempotent rather
    than duplicative.
    """
    path = Path(path)
    content = path.read_text()
    atype = artifact_type or infer_artifact_type(path)
    return Artifact(
        id=deterministic_id("artifact", atype.value, content),
        type=atype,
        source=path,
        content=content,
        recorded_at=recorded_at,
    )


@dataclass
class IngestResult:
    artifact: Artifact
    compiled: CompiledArtifact
    delta: MemoryDelta

    @property
    def summary(self) -> str:
        name = self.artifact.source.name if self.artifact.source else self.artifact.id[:16]
        return (
            f"{name:<34} entities={len(self.compiled.entities):<3} "
            f"facts={len(self.compiled.facts):<3} relations={len(self.compiled.relations):<3} "
            f"-> new={len(self.delta.promoted_facts):<3} "
            f"evidence={len(self.delta.evidence_records):<3} "
            f"superseded={len(self.delta.supersessions):<2} "
            f"conflicts={len(self.delta.conflicts)}"
        )


@dataclass
class Ingestor:
    """Compiler + linker + store, wired once."""
    memory: ProjectMemory
    compiler: MemoryCompiler = field(default_factory=MemoryCompiler)
    linker: ThreePassMemoryPatchLinker = field(default_factory=ThreePassMemoryPatchLinker)

    def ingest(self, artifact: Artifact) -> IngestResult:
        compiled = self.compiler.compile(artifact)
        delta = self.linker.link(self.memory, compiled)
        self.memory.apply_delta(delta)
        return IngestResult(artifact=artifact, compiled=compiled, delta=delta)

    def ingest_file(
        self,
        path: str | Path,
        artifact_type: ArtifactType | None = None,
        recorded_at: str = "",
    ) -> IngestResult:
        return self.ingest(load_artifact(path, artifact_type, recorded_at))

    def ingest_scenario(self, directory: str | Path) -> list[IngestResult]:
        """
        Ingest a scenario directory.

        A `manifest.json` lists each artifact with its type and timestamp:

            {"artifacts": [
                {"file": "adr-004.md", "type": "adr", "recorded_at": "2023-01-11"}
            ]}

        Without a manifest, files are ingested in sorted order with inferred
        types and no timestamps - which means any supersession they cause will
        be ordered by ingestion, and the resolver will say so.
        """
        directory = Path(directory)
        manifest_path = directory / MANIFEST_NAME

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            return [
                self.ingest_file(
                    directory / entry["file"],
                    ArtifactType(entry["type"]) if "type" in entry else None,
                    entry.get("recorded_at", ""),
                )
                for entry in manifest["artifacts"]
            ]

        return [
            self.ingest_file(path)
            for path in sorted(directory.glob("*.md"))
        ]
