"""
Relational patterns.

One table, consumed by two extractors:

    RelationalStatementExtractor  turns a match into (subject, predicate, object)
    PhraseEntityRecognizer        registers the matched phrases as entities

They share this table so a phrase can never be extracted as a fact operand
without also existing as an entity - which is exactly the failure the read path
exposed: entities and facts living in disjoint graphs.

These patterns are deliberately naive and deliberately deterministic. They are
a floor, not a ceiling: an LLM extractor implementing the same StatementExtractor
interface can replace them without any change below the compiler. What matters
architecturally is the SHAPE of the output - (entity, predicate, entity) - not
the sophistication of the matcher.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A captured phrase is cut at the first of these, so
# "service-to-service authentication across all internal services"
# normalizes to "service-to-service authentication".
_TAIL_MARKERS = (
    " across ", " because ", " since ", " which ", " that ", " while ",
    " in order to ", " so that ", " when ", " unless ", " rather than ",
    " instead of ", " as part of ", " for all ", " on every ",
)

_LEADING_ARTICLES = re.compile(r"^(?:the|a|an|our|its|their)\s+", re.IGNORECASE)

# Phrases that are grammatical filler, never a project concept.
_STOP_PHRASES = {
    "it", "this", "that", "them", "us", "we", "everything", "anything",
    "all services", "all of them",
}


def normalize_phrase(raw: str) -> str:
    """
    Deterministic phrase normalization. Documented and total: same input always
    yields the same output, and the transformation list is short enough to read.
    """
    text = " ".join(raw.split())
    lowered = text.lower()
    for marker in _TAIL_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            text = text[:idx]
            lowered = text.lower()
    text = _LEADING_ARTICLES.sub("", text).strip()
    text = text.strip(" .,:;\"'()[]")
    return " ".join(text.split())


def is_usable_phrase(phrase: str) -> bool:
    if not phrase or len(phrase) < 2:
        return False
    if phrase.lower() in _STOP_PHRASES:
        return False
    # A whole sentence is not a concept.
    return len(phrase.split()) <= 6


@dataclass(frozen=True, slots=True)
class RelationalPattern:
    """
    One surface pattern.

    `subject_group` / `object_group` are 1-based regex group indices. Swapping
    them is how "Use X for Y" becomes (Y selected X) rather than (X selected Y):
    the capability is the subject of a decision, the technology is the object.
    """
    name: str
    regex: re.Pattern[str]
    predicate: str
    subject_group: int
    object_group: int


# Phrase fragment. Non-greedy and terminated by punctuation, so a match stops
# at the first clause boundary rather than running across sentences. The upper
# bound is generous because `normalize_phrase` trims the tail afterwards and
# `is_usable_phrase` rejects anything still longer than six words.
_P = r"([A-Za-z0-9][\w\.\-/ ]{1,90}?)"

RELATIONAL_PATTERNS: tuple[RelationalPattern, ...] = (
    RelationalPattern(
        "replace_with",
        re.compile(rf"\breplac(?:e|es|ed|ing)\s+{_P}\s+with\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "replaced_by", 1, 2,
    ),
    RelationalPattern(
        "use_for",
        re.compile(rf"\bus(?:e|es|ed|ing)\s+{_P}\s+for\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "selected", 2, 1,
    ),
    RelationalPattern(
        "adopt_for",
        re.compile(rf"\badopt(?:s|ed|ing)?\s+{_P}\s+for\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "selected", 2, 1,
    ),
    RelationalPattern(
        "migrate_to",
        re.compile(rf"\bmigrat(?:e|es|ed|ing)\s+{_P}\s+to\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "uses", 1, 2,
    ),
    RelationalPattern(
        "move_into",
        re.compile(rf"\bmov(?:e|es|ed|ing)\s+{_P}\s+(?:into|to)\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "contains", 2, 1,
    ),
    RelationalPattern(
        "remove_from",
        re.compile(rf"\bremov(?:e|es|ed|ing)\s+{_P}\s+from\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "removes", 2, 1,
    ),
    RelationalPattern(
        "depends_on",
        re.compile(rf"{_P}\s+depends?\s+on\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "depends_on", 1, 2,
    ),
    RelationalPattern(
        "requires",
        re.compile(rf"{_P}\s+requires?\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "requires", 1, 2,
    ),
    RelationalPattern(
        "uses",
        re.compile(rf"{_P}\s+uses\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "uses", 1, 2,
    ),
    RelationalPattern(
        "deprecates",
        re.compile(rf"\bdeprecat(?:e|es|ed|ing)\s+{_P}\s+in\s+favou?r\s+of\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "replaced_by", 1, 2,
    ),
)


@dataclass(frozen=True, slots=True)
class PatternMatch:
    pattern_name: str
    predicate: str
    subject: str
    object: str


def find_relational_matches(text: str) -> list[PatternMatch]:
    """
    All usable relational matches in a piece of text, in pattern-table order.
    Deterministic: no ordering depends on dict iteration or set traversal.
    """
    matches: list[PatternMatch] = []
    seen: set[tuple[str, str, str]] = set()

    for pattern in RELATIONAL_PATTERNS:
        for match in pattern.regex.finditer(text):
            subject = normalize_phrase(match.group(pattern.subject_group))
            obj = normalize_phrase(match.group(pattern.object_group))
            if not (is_usable_phrase(subject) and is_usable_phrase(obj)):
                continue
            if subject.lower() == obj.lower():
                continue
            key = (subject.lower(), pattern.predicate, obj.lower())
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                PatternMatch(
                    pattern_name=pattern.name,
                    predicate=pattern.predicate,
                    subject=subject,
                    object=obj,
                )
            )
    return matches
