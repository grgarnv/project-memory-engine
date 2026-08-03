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

# Modals and adverbs get swallowed into a capture because they sit between the
# subject and the verb: "The compiler never imports" captures "compiler never".
# Trimmed from the tail so the operand is the concept, not the concept plus the
# grammar that happened to precede the verb. The negation itself is detected on
# the whole sentence, so trimming here loses nothing.
_TRAILING_MODIFIERS = frozenset({
    "never", "not", "may", "must", "should", "shall", "can", "could", "will",
    "would", "might", "now", "also", "always", "only", "still", "then", "yet",
    "already", "currently", "explicitly", "deliberately", "simply", "just",
    "longer", "ever", "once", "often", "sometimes", "generally", "no",
    "is", "are", "was", "were", "be", "been", "does", "do", "did", "has", "have",
})

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

    tokens = text.split()
    while len(tokens) > 1 and tokens[-1].lower() in _TRAILING_MODIFIERS:
        tokens.pop()
    return " ".join(tokens)


def is_usable_phrase(phrase: str) -> bool:
    if not phrase or len(phrase) < 2:
        return False
    if phrase.lower() in _STOP_PHRASES:
        return False
    # A whole sentence is not a concept.
    return len(phrase.split()) <= 6


# ---------------------------------------------------------------------------
# Operand quality
# ---------------------------------------------------------------------------
#
# Running against real prose (this repository's own RFCs) produced operands like
# "and no corpus" and "so neither side": the capture had grabbed a clause
# fragment. A relational pattern matching is not sufficient evidence that its
# operands are concepts. These gates are the precision half of extraction.

# A phrase beginning with one of these is a clause fragment, not a concept.
_LEADING_STOPWORDS = frozenset({
    "and", "or", "but", "so", "then", "thus", "therefore", "however",
    "that", "which", "who", "whom", "whose", "what", "when", "where",
    "if", "unless", "because", "since", "while", "although", "though",
    "neither", "either", "nor", "not", "no", "none", "any", "some",
    "this", "these", "those", "it", "they", "them", "he", "she", "we", "you",
    "each", "every", "both", "all", "such", "there", "here", "also",
    "only", "just", "even", "still", "yet", "now", "never", "always",
    "be", "been", "being", "is", "are", "was", "were", "do", "does", "did",
    "can", "may", "might", "must", "should", "would", "could", "will",
})

# Head nouns that make a lowercase phrase a plausible project concept. Without
# one, a phrase needs an uppercase letter or digit to qualify - which is what
# most technical names have.
_DOMAIN_HEADS = frozenset({
    "authentication", "authorization", "auth", "encryption", "validation",
    "caching", "cache", "logging", "monitoring", "tracing", "metrics",
    "service", "services", "gateway", "api", "apis", "endpoint", "endpoints",
    "database", "store", "storage", "queue", "topic", "index", "schema",
    "compiler", "linker", "resolver", "parser", "extractor", "pipeline",
    "module", "package", "library", "framework", "component", "layer",
    "memory", "session", "token", "tokens", "key", "keys", "credential",
    "credentials", "request", "requests", "response", "job", "worker",
    "migration", "deployment", "cluster", "node", "registry", "ontology",
    "contract", "contracts", "test", "tests", "suite", "client", "server",
    "protocol", "format", "backend", "frontend", "ui", "cli", "sdk",
})


def _is_concept(phrase: str) -> bool:
    """
    Does this phrase plausibly name a project concept?

    Three ways to qualify:

      1. It looks technical - an uppercase letter or a digit somewhere.
      2. Its head noun is domain vocabulary.
      3. It is a multi-word phrase containing no grammatical filler.

    Rule 3 exists because rules 1 and 2 are a closed vocabulary, and a closed
    vocabulary silently fails on every project that names things differently.
    The first version of this gate had no rule 3 and dropped "web tier" - it
    scored 100% precision and 38% recall, with every miss being one unlisted
    head noun. Evaluation caught that; reading the output would not have.

    Filler is still rejected anywhere in the phrase, not only at the front, so
    "some other thing" and "no corpus" do not qualify on length alone.
    """
    tokens = phrase.split()
    if not tokens:
        return False
    lowered = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tokens]
    if lowered[0] in _LEADING_STOPWORDS:
        return False
    if any(c.isupper() or c.isdigit() for c in phrase):
        return True
    if lowered[-1] in _DOMAIN_HEADS:
        return True
    return len(tokens) >= 2 and not any(t in _LEADING_STOPWORDS for t in lowered)


# ---------------------------------------------------------------------------
# Sentences and negation
# ---------------------------------------------------------------------------
#
# Patterns used to run against a whole paragraph, which let a capture span a
# sentence boundary and let one match per pattern shadow the rest. Splitting
# first raises both precision and recall.

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"'(\[])")

# Abbreviations that end in a period without ending a sentence.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "cf.", "vs.", "Fig.", "No.")


def split_sentences(text: str) -> list[str]:
    protected = text
    for i, abbr in enumerate(_ABBREVIATIONS):
        protected = protected.replace(abbr, f"\x00{i}\x00")
    parts = _SENTENCE_SPLIT.split(protected)
    restored = []
    for part in parts:
        for i, abbr in enumerate(_ABBREVIATIONS):
            part = part.replace(f"\x00{i}\x00", abbr)
        part = part.strip()
        if part:
            restored.append(part)
    return restored


_NEGATION = re.compile(
    r"\b(never|not|cannot|can't|won't|must not|may not|does not|do not|"
    r"should not|shall not|no longer|neither|nor)\b",
    re.IGNORECASE,
)

# Predicates asserting that something is in use. Negating one is a constraint,
# not an absence of information: "the linker never calls an LLM" is a rule the
# project holds, and PROHIBITS is exactly the ontology term for it.
_NEGATABLE = {"uses", "imports", "calls", "depends_on", "requires", "contains"}


def is_negated(clause: str) -> bool:
    return bool(_NEGATION.search(clause))


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
    RelationalPattern(
        "imports",
        re.compile(rf"{_P}\s+(?:may\s+)?imports?\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "imports", 1, 2,
    ),
    RelationalPattern(
        "implements",
        re.compile(rf"{_P}\s+implements?\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "implements", 1, 2,
    ),
    RelationalPattern(
        "extends",
        re.compile(rf"{_P}\s+extends\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "extends", 1, 2,
    ),
    RelationalPattern(
        "calls",
        re.compile(rf"{_P}\s+calls\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "calls", 1, 2,
    ),
    RelationalPattern(
        "contains",
        re.compile(rf"{_P}\s+contains\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "contains", 1, 2,
    ),
    RelationalPattern(
        "exposes",
        re.compile(rf"{_P}\s+exposes\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "exposes", 1, 2,
    ),
    RelationalPattern(
        "built_on",
        re.compile(rf"{_P}\s+(?:is\s+)?(?:built\s+on|sits\s+on\s+top\s+of|"
                   rf"runs\s+on|is\s+backed\s+by)\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "depends_on", 1, 2,
    ),
    RelationalPattern(
        "replaces",
        re.compile(rf"{_P}\s+(?:now\s+)?replaces\s+{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "replaced_by", 2, 1,
    ),
    RelationalPattern(
        "aka",
        re.compile(rf"{_P}\s*[\(,]\s*(?:a\.?k\.?a\.?|also\s+(?:known\s+as|called))\s+"
                   rf"{_P}\s*[\),\.;]", re.IGNORECASE),
        "same_as", 1, 2,
    ),
    RelationalPattern(
        "also_known_as",
        re.compile(rf"{_P}\s+is\s+(?:also\s+)?(?:known\s+as|called|referred\s+to\s+as)\s+"
                   rf"{_P}(?:[\.,;]|$)", re.IGNORECASE),
        "same_as", 1, 2,
    ),
    RelationalPattern(
        "same_thing_as",
        re.compile(rf"{_P}\s+(?:is\s+the\s+same\s+(?:thing\s+)?as|and)\s+{_P}\s+"
                   rf"are\s+the\s+same(?:\s+\w+)?(?:[\.,;]|$)", re.IGNORECASE),
        "same_as", 1, 2,
    ),
    RelationalPattern(
        "prefer_over",
        re.compile(rf"\b(?:prefer|choose|chose|selected)\s+{_P}\s+over\s+{_P}(?:[\.,;]|$)",
                   re.IGNORECASE),
        "rejected", 1, 2,
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
    All usable relational matches, sentence by sentence.

    Deterministic throughout: sentences in document order, patterns in table
    order, no ordering that depends on dict or set traversal.
    """
    matches: list[PatternMatch] = []
    seen: set[tuple[str, str, str]] = set()

    for sentence in split_sentences(text):
        negated = is_negated(sentence)

        for pattern in RELATIONAL_PATTERNS:
            for match in pattern.regex.finditer(sentence):
                subject = normalize_phrase(match.group(pattern.subject_group))
                obj = normalize_phrase(match.group(pattern.object_group))

                if not (is_usable_phrase(subject) and is_usable_phrase(obj)):
                    continue
                if not (_is_concept(subject) and _is_concept(obj)):
                    continue
                if subject.lower() == obj.lower():
                    continue

                predicate = pattern.predicate
                if negated:
                    # A negated currency claim is a constraint the project
                    # holds, not missing information. Anything else negated is
                    # dropped rather than inverted into a fact nobody asserted.
                    if predicate not in _NEGATABLE:
                        continue
                    predicate = "prohibits"

                key = (subject.lower(), predicate, obj.lower())
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    PatternMatch(
                        pattern_name=pattern.name,
                        predicate=predicate,
                        subject=subject,
                        object=obj,
                    )
                )
    return matches
