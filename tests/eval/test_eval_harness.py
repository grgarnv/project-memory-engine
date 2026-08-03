"""
The evaluation harness.

Extraction decisions were being made on impressions until this existed. The
first run of it caught a precision gate that scored 100% precision and 38%
recall because one head noun was missing from a closed vocabulary.
"""
import pytest

from memory_engine.eval import load_cases, run_all, run_case
from memory_engine.eval.harness import Scores, format_report
from tests.conftest import REPO_ROOT

EVAL_ROOT = REPO_ROOT / "fixtures" / "eval"

# Floors, not targets. They exist to catch regression, and they are set below
# current numbers so that ordinary tuning does not require editing the test.
# Raising them to match whatever the extractor currently scores would make the
# suite a mirror rather than a check.
MIN_PRECISION = 0.85
MIN_RECALL = 0.60


def test_cases_are_discovered():
    assert load_cases(EVAL_ROOT), "no evaluation cases found"


def test_labels_include_assertions_the_extractor_cannot_reach():
    """
    A label set containing only reachable triples reports 100% recall and hides
    the gap. At least one case must be honest about its ceiling.
    """
    assert any(case.unreachable for case in load_cases(EVAL_ROOT))


@pytest.mark.parametrize("case", load_cases(EVAL_ROOT), ids=lambda c: c.name)
def test_case_meets_the_floor(case):
    result = run_case(case)
    assert result.overall.precision >= MIN_PRECISION, result.spurious
    assert result.reachable.recall >= MIN_RECALL, result.missed


def test_aggregate_is_reported():
    results = run_all(EVAL_ROOT)
    report = format_report(results)
    assert "TOTAL overall" in report
    assert "TOTAL reachable" in report


def test_scores_arithmetic():
    a = Scores(true_positives=3, false_positives=1, false_negatives=1)
    b = Scores(true_positives=1, false_positives=0, false_negatives=2)
    total = a + b
    assert (total.true_positives, total.false_positives, total.false_negatives) == (4, 1, 3)
    assert Scores().f1 == 0.0


def test_evaluation_is_reproducible():
    """Same corpus, same labels, same numbers - or the harness measures nothing."""
    first = run_all(EVAL_ROOT)
    second = run_all(EVAL_ROOT)
    assert [r.overall.f1 for r in first] == [r.overall.f1 for r in second]
