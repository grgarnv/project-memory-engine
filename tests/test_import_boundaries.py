"""
Architectural boundaries, enforced.

Three RFCs state that the compiler is stateless and history-free, that the
linker never reaches into a store's internals, and that the read path does not
depend on the write path. Until this file existed those were prose. Now they
are assertions.

Walk the AST of every module and check what it imports.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "memory_engine"


def _modules(subpath: str) -> list[Path]:
    root = PACKAGE / subpath if subpath else PACKAGE
    return sorted(p for p in root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _assert_no_import(path: Path, forbidden: tuple[str, ...]) -> None:
    for imported in _imports(path):
        for bad in forbidden:
            assert not imported.startswith(bad), (
                f"{path.relative_to(PACKAGE.parent)} imports {imported}; "
                f"{bad} is out of bounds for this layer"
            )


@pytest.mark.parametrize("path", _modules("compiler"), ids=lambda p: p.name)
def test_compiler_is_history_free(path):
    """The compiler may know ir and ontology. Nothing about memory or history."""
    _assert_no_import(path, (
        "memory_engine.linker",
        "memory_engine.store",
        "memory_engine.resolve",
        "memory_engine.memory",
        "memory_engine.ingest",
    ))


@pytest.mark.parametrize("path", _modules("linker"), ids=lambda p: p.name)
def test_linker_depends_on_contracts_not_stores(path):
    """The linker talks to MemoryReader, never to a concrete store."""
    _assert_no_import(path, (
        "memory_engine.store",
        "memory_engine.resolve",
        "memory_engine.compiler",
    ))


@pytest.mark.parametrize("path", _modules("resolve"), ids=lambda p: p.name)
def test_read_path_does_not_depend_on_write_path(path):
    """The resolver reads the schema. It knows nothing about how facts got there."""
    _assert_no_import(path, (
        "memory_engine.compiler",
        "memory_engine.linker",
        "memory_engine.store",
        "memory_engine.ingest",
    ))


@pytest.mark.parametrize("path", _modules("memory"), ids=lambda p: p.name)
def test_schema_depends_on_nothing(path):
    """The spine imports no layer at all - both sides depend on it, not it on them."""
    _assert_no_import(path, (
        "memory_engine.compiler",
        "memory_engine.linker",
        "memory_engine.store",
        "memory_engine.resolve",
        "memory_engine.ingest",
        "memory_engine.ir",
    ))


def test_llm_is_quarantined_to_the_compiler():
    """
    Determinism below the compiler is only meaningful if nothing below it can
    call a model. RFC 003 non-goal 2, enforced.
    """
    for layer in ("linker", "store", "resolve", "memory"):
        for path in _modules(layer):
            _assert_no_import(path, ("memory_engine.compiler.extractors.llm",))
