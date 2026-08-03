"""
Persistent memory schema and store contracts.

The spine of the system. The linker writes these types, the resolver reads
them, stores implement them. This package imports nothing from linker, store,
compiler, or resolve.
"""
from memory_engine.memory.contracts import (
    BeliefReader,
    MemoryReader,
    MemoryWriter,
    ProjectMemory,
)
from memory_engine.memory.model import (
    ArtifactRef,
    ConflictEdge,
    EvidenceRecord,
    GlobalEntityBinding,
    MemoryDelta,
    PersistedFact,
    SupersessionEdge,
    is_artifact_ref,
)

__all__ = [
    "ArtifactRef",
    "is_artifact_ref",
    "GlobalEntityBinding",
    "EvidenceRecord",
    "PersistedFact",
    "SupersessionEdge",
    "ConflictEdge",
    "MemoryDelta",
    "MemoryReader",
    "BeliefReader",
    "MemoryWriter",
    "ProjectMemory",
]
