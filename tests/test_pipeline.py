import json
from pathlib import Path

import pytest

from memory_engine.ir import Artifact, ArtifactType
from memory_engine.pipeline import MemoryCompiler

GOLDEN_DIR = Path(__file__).parent / "golden"
CASES = sorted(p.name for p in GOLDEN_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("case", CASES)
def test_golden_statements(case):
    case_dir = GOLDEN_DIR / case

    artifact = Artifact(
        type=ArtifactType.PR,
        content=(case_dir / "input.md").read_text(),
    )
    expected_raw = json.loads((case_dir / "expected.json").read_text())
    expected_statements = expected_raw["statements"]

    result = MemoryCompiler().compile(artifact)

    actual = [
        {"subject": s.subject, "predicate": s.predicate, "target": s.target}
        for s in result["statements"]
    ]

    assert actual == expected_statements

    if "fact_count" in expected_raw:
        assert len(result["facts"]) == expected_raw["fact_count"]
