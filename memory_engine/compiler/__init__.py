"""
The compiler: stateless, reproducible transformation of one artifact into IR.

Knows nothing about project history, other artifacts, or persistent memory.
"""
from memory_engine.compiler.pipeline import (
    COMPILER_VERSION,
    MemoryCompiler,
    extract_claims,
    extract_entities,
    extract_facts,
    extract_relations,
    extract_statements,
    observe,
    resolve_entities,
    segment,
)

__all__ = [
    "MemoryCompiler",
    "COMPILER_VERSION",
    "observe",
    "segment",
    "extract_statements",
    "extract_entities",
    "extract_claims",
    "extract_facts",
    "resolve_entities",
    "extract_relations",
]
