"""
Extraction precision and negation.

Written after running the engine against this repository's own documentation.
The fixtures had been authored by someone who knew the pattern table; real prose
produced operands like "and no corpus" and "so neither side" - a pattern
matching is not evidence that its operands are concepts.
"""
import pytest

from memory_engine.compiler.extractors.patterns import (
    find_relational_matches,
    is_negated,
    normalize_phrase,
    split_sentences,
)
from memory_engine.ontology import Predicate
from tests.conftest import make_artifact


@pytest.mark.parametrize("text", [
    "so neither side depends on the other, and no corpus to reprocess.",
    "This means that it uses them.",
    "and no corpus uses reprocess.",
    "There are none, so all of them depend on that.",
])
def test_clause_fragments_are_not_concepts(text):
    """The precision regression guard. These all produced facts before."""
    assert find_relational_matches(text) == []


@pytest.mark.parametrize("text,triple", [
    ("The API Gateway uses OAuth2.", ("API Gateway", "uses", "OAuth2")),
    ("The linker depends on the memory contracts.",
     ("linker", "depends_on", "memory contracts")),
    ("The resolver is built on the memory contracts.",
     ("resolver", "depends_on", "memory contracts")),
    ("OAuth2 now replaces JWT.", ("JWT", "replaced_by", "OAuth2")),
])
def test_real_assertions_still_extract(text, triple):
    assert triple in [(m.subject, m.predicate, m.object)
                      for m in find_relational_matches(text)]


def test_negated_currency_claim_becomes_a_constraint():
    """
    "The compiler never imports the linker" is a rule the project holds, not
    missing information. Dropping it loses a real fact; inverting it into
    `imports` would be a fabrication. PROHIBITS is the ontology term for it.
    """
    matches = find_relational_matches("The compiler never imports the linker.")
    assert [(m.subject, m.predicate, m.object) for m in matches] == [
        ("compiler", "prohibits", "linker")
    ]


def test_negation_of_a_non_currency_predicate_is_dropped_not_inverted():
    assert find_relational_matches("The compiler does not replace JWT with OAuth2.") == []


def test_modals_are_trimmed_from_operands():
    """"The compiler never imports" captures "compiler never" without this."""
    assert normalize_phrase("compiler never") == "compiler"
    assert normalize_phrase("the resolver must") == "resolver"
    assert normalize_phrase("compiler") == "compiler"


def test_sentences_are_split_before_matching():
    text = "The gateway uses OAuth2. The linker depends on the contracts."
    assert len(split_sentences(text)) == 2
    assert len(find_relational_matches(text)) == 2


def test_abbreviations_do_not_split_sentences():
    assert len(split_sentences("Use Redis, e.g. for caching. Then stop.")) == 2


def test_capture_cannot_span_a_sentence_boundary():
    text = "We deployed the API Gateway. Redis uses a lot of memory."
    subjects = {m.subject for m in find_relational_matches(text)}
    assert not any("Gateway" in s and "Redis" in s for s in subjects)


@pytest.mark.parametrize("clause,expected", [
    ("the linker never calls an LLM", True),
    ("the resolver must not mutate memory", True),
    ("the compiler imports the ontology", False),
])
def test_negation_detection(clause, expected):
    assert is_negated(clause) is expected


# ---------------------------------------------------------------------------
# Markdown structure
# ---------------------------------------------------------------------------

def test_code_fences_are_not_assertions(compiler):
    """A code block parsed as prose produced junk facts on every doc."""
    content = (
        "The gateway uses OAuth2.\n\n"
        "```python\nx = compute()  # the cache uses Redis\n```\n\n"
        "Done.\n"
    )
    result = compiler.compile(make_artifact(content))
    assert all("compute()" not in f.object for f in result["facts"])


def test_table_rows_are_dropped(compiler):
    content = "Intro text.\n\n| Component | Role |\n|---|---|\n| linker | writes |\n"
    result = compiler.compile(make_artifact(content))
    assert all("|" not in f.object for f in result["facts"])


def test_each_bullet_is_its_own_assertion(compiler):
    """A list collapsed into one paragraph yields one fact for several claims."""
    content = (
        "Constraints:\n\n"
        "- The API Gateway uses OAuth2.\n"
        "- The linker depends on the memory contracts.\n"
    )
    result = compiler.compile(make_artifact(content))
    predicates = {f.predicate for f in result["facts"]}
    assert Predicate.USES in predicates
    assert Predicate.DEPENDS_ON in predicates
