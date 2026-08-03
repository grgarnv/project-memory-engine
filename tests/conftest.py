"""Shared fixtures."""
from pathlib import Path

import pytest

from memory_engine.compiler import MemoryCompiler
from memory_engine.ingest import Ingestor
from memory_engine.ir import Artifact, ArtifactType, deterministic_id
from memory_engine.linker import ThreePassMemoryPatchLinker
from memory_engine.store import InMemoryProjectMemory, SQLiteProjectMemory

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "fixtures"
SCENARIOS = FIXTURES / "scenarios"
GOLDEN = Path(__file__).parent / "compiler" / "golden"


def make_artifact(content: str, atype: ArtifactType = ArtifactType.PR,
                  recorded_at: str = "") -> Artifact:
    return Artifact(
        id=deterministic_id("artifact", atype.value, content),
        type=atype,
        content=content,
        recorded_at=recorded_at,
    )


@pytest.fixture
def compiler() -> MemoryCompiler:
    return MemoryCompiler()


@pytest.fixture
def linker() -> ThreePassMemoryPatchLinker:
    return ThreePassMemoryPatchLinker()


@pytest.fixture
def memory() -> InMemoryProjectMemory:
    return InMemoryProjectMemory()


@pytest.fixture
def ingestor(memory) -> Ingestor:
    return Ingestor(memory=memory)


@pytest.fixture(params=["in_memory", "sqlite"])
def any_store(request, tmp_path):
    """Every store implementation, for contract conformance."""
    if request.param == "in_memory":
        yield InMemoryProjectMemory()
    else:
        store = SQLiteProjectMemory(tmp_path / "memory.db")
        yield store
        store.close()
