"""
The linker.

Stateful counterpart to the compiler. Consumes one CompiledArtifact and emits a
MemoryDelta to be applied to persistent memory.

    CompiledArtifact
        -> BindingPass       local entities -> global IDs
        -> PersistencePass   facts -> PersistedFact + EvidenceRecord
        -> AnalysisPipeline  supersession and conflict edges
        -> MemoryDelta

Non-goals, unchanged from RFC 003:
  never parses documents, never calls an LLM, never does vector retrieval,
  never guesses unresolved entities, never mutates compiler output, never
  deletes anything, never invents ontology.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from memory_engine.ir import CompiledArtifact
from memory_engine.linker.passes import AnalysisPipeline, BindingPass, PersistencePass
from memory_engine.memory.contracts import MemoryReader
from memory_engine.memory.model import MemoryDelta


class MemoryPatchLinker(ABC):
    @abstractmethod
    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        ...


class ThreePassMemoryPatchLinker(MemoryPatchLinker):
    def __init__(self, analysis_pipeline: AnalysisPipeline | None = None):
        self.binding_pass = BindingPass()
        self.persistence_pass = PersistencePass()
        self.analysis_pipeline = analysis_pipeline or AnalysisPipeline()

    def link(self, reader: MemoryReader, compiled_artifact: CompiledArtifact) -> MemoryDelta:
        binding = self.binding_pass.bind(reader, compiled_artifact)
        delta = self.persistence_pass.persist(reader, compiled_artifact, binding)
        self.analysis_pipeline.execute(reader, delta)
        return delta
