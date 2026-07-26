"""
Project Memory Engine
"""
from memory_engine.ir import Artifact, ArtifactType, Observation, Segment, Statement, Entity, Claim, Fact, Relation, CompiledArtifact
from memory_engine.ontology import EntityType, Predicate, OntologyVersion, OntologyRegistry
from memory_engine.pipeline import MemoryCompiler
from memory_engine.patch import (
    ArtifactRef,
    GlobalEntityBinding,
    EvidenceRecord,
    PersistedFact,
    SupersessionEdge,
    ConflictEdge,
    MemoryDelta,
    MemoryReader,
    MemoryPatchLinker,
    ThreePassMemoryPatchLinker,
    BindingPass,
    PersistencePass,
    AnalysisRule,
    AnalysisPipeline,
    ExplicitDeprecationRule,
    SingleOccupancyDecisionRule,
    DirectNegationConflictRule,
    InMemoryProjectMemory,
)

__all__ = [
    "Artifact",
    "ArtifactType",
    "Observation",
    "Segment",
    "Statement",
    "Entity",
    "Claim",
    "Fact",
    "Relation",
    "CompiledArtifact",
    "EntityType",
    "Predicate",
    "OntologyVersion",
    "OntologyRegistry",
    "MemoryCompiler",
    "ArtifactRef",
    "GlobalEntityBinding",
    "EvidenceRecord",
    "PersistedFact",
    "SupersessionEdge",
    "ConflictEdge",
    "MemoryDelta",
    "MemoryReader",
    "MemoryPatchLinker",
    "ThreePassMemoryPatchLinker",
    "BindingPass",
    "PersistencePass",
    "AnalysisRule",
    "AnalysisPipeline",
    "ExplicitDeprecationRule",
    "SingleOccupancyDecisionRule",
    "DirectNegationConflictRule",
    "InMemoryProjectMemory",
]

