"""
Project Memory Engine

A compiler-based system that gives a software project a persistent, evolving
model of its own knowledge.

    memory_engine.ontology   the fixed vocabulary
    memory_engine.ir         compiler intermediate representation
    memory_engine.compiler   stateless artifact -> IR
    memory_engine.memory     persistent schema + store contracts
    memory_engine.linker     stateful IR -> memory delta
    memory_engine.store      store implementations (in-memory, SQLite)
    memory_engine.resolve    memory -> current belief, with evidence
    memory_engine.ingest     the wiring

Dependency direction:

    ontology <- ir <- compiler
    ontology <- memory <- linker
                memory <- store
                memory <- resolve

compiler never imports linker, store, or resolve.
resolve never imports compiler or linker.
Enforced by tests/test_import_boundaries.py.
"""
__version__ = "0.3.0"

from memory_engine.compiler import MemoryCompiler
from memory_engine.ingest import Ingestor, load_artifact
from memory_engine.ir import Artifact, ArtifactType
from memory_engine.linker import ThreePassMemoryPatchLinker
from memory_engine.resolve import BeliefResolver, render
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory

__all__ = [
    "__version__",
    "Artifact",
    "ArtifactType",
    "MemoryCompiler",
    "ThreePassMemoryPatchLinker",
    "InMemoryProjectMemory",
    "SQLiteProjectMemory",
    "BeliefResolver",
    "render",
    "Ingestor",
    "load_artifact",
]
