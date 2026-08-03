"""
Explanation.

Turns a `ResolvedBelief` into prose a person can read without knowing the
schema. This is the layer the vision doc describes — "the project should already
know" — and it is deliberately thin.

Every sentence here is a rendering of a value the resolver produced. There is no
model call, no summarization, and no inference: if the explanation says a
decision was made in a particular artifact on a particular date, that artifact
and date came from an `EvidenceRecord`. If memory does not know something, the
explanation says so rather than smoothing over it.

The temptation this file exists to resist is generating fluent text that is
slightly more confident than the evidence supports. Fluency is not the goal;
faithfulness is. Where the two conflict, the sentence gets uglier.
"""
from __future__ import annotations

from memory_engine.ontology import Predicate
from memory_engine.resolve.resolver import BeliefNode, ResolvedBelief

# How each predicate reads in a sentence, active voice, subject first.
_PHRASING: dict[Predicate, str] = {
    Predicate.SELECTED: "uses {object} for {subject}",
    Predicate.REJECTED: "rejected {object} for {subject}",
    Predicate.REPLACED_BY: "replaced {subject} with {object}",
    Predicate.DEPRECATED: "deprecated {subject}",
    Predicate.USES: "{subject} uses {object}",
    Predicate.DEPENDS_ON: "{subject} depends on {object}",
    Predicate.REQUIRES: "{subject} requires {object}",
    Predicate.PROHIBITS: "{subject} must not use {object}",
    Predicate.ALLOWS: "{subject} may use {object}",
    Predicate.CONTAINS: "{subject} contains {object}",
    Predicate.IMPLEMENTS: "{subject} implements {object}",
    Predicate.IMPORTS: "{subject} imports {object}",
    Predicate.CALLS: "{subject} calls {object}",
    Predicate.EXPOSES: "{subject} exposes {object}",
    Predicate.EXTENDS: "{subject} extends {object}",
    Predicate.REMOVES: "{subject} removes {object}",
    Predicate.HAS_REASON: "the stated reason is: {object}",
    Predicate.HAS_TRADEOFF: "the stated trade-off is: {object}",
    Predicate.HAS_BENEFIT: "the stated benefit is: {object}",
    Predicate.HAS_RISK: "the stated risk is: {object}",
}

_ARTIFACT_NOUN = {
    "adr": "an ADR",
    "pull_request": "a pull request",
    "commit": "a commit",
    "issue": "an issue",
    "document": "a document",
    "slack": "a Slack message",
    "code": "code",
}


def phrase(node: BeliefNode) -> str:
    template = _PHRASING.get(node.predicate)
    if template is None:
        return f"{node.subject_label} {node.predicate.value.replace('_', ' ')} {node.object_label}"
    return template.format(subject=node.subject_label, object=node.object_label)


def _evidence_clause(node: BeliefNode) -> str:
    """
    Describe the support without overstating it.

    One artifact is "asserted by"; several is "corroborated by". A single
    undated commit message and three dated ADRs must not read the same way.
    """
    if not node.evidence:
        return "no recorded evidence"

    counts: dict[str, int] = {}
    for ev in node.evidence:
        counts[ev.artifact_type] = counts.get(ev.artifact_type, 0) + 1

    parts = []
    for atype, count in sorted(counts.items()):
        noun = _ARTIFACT_NOUN.get(atype, atype)
        if count == 1:
            parts.append(noun)
        else:
            plural = noun.split(" ", 1)[-1] + "s" if " " in noun else noun + "s"
            parts.append(f"{count} {plural}")

    support = " and ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
    verb = "asserted by" if len(node.evidence) == 1 else "corroborated by"

    when = node.last_asserted
    tail = f", most recently on {when}" if when else ", none of it dated"
    return f"{verb} {support}{tail}"


def explain(belief: ResolvedBelief) -> str:
    """Prose answer. Every claim traces to a value in the resolved belief."""
    subject = belief.identity.canonical_label if belief.identity else belief.query

    if not belief.answered:
        reason = belief.diagnostics[0] if belief.diagnostics else "Memory holds nothing about it."
        return f"The project has no recorded position on {belief.query!r}. {reason}"

    paragraphs: list[str] = []

    # 1. What is believed now.
    decision = belief.decision
    if decision is not None:
        opening = f"The project {phrase(decision)}."
        opening += f" That position is {_evidence_clause(decision)}."
        paragraphs.append(opening)
    else:
        claims = "; ".join(phrase(n) for n in belief.current[:4])
        paragraphs.append(f"What the project records about {subject}: {claims}.")

    # 2. Rationale, kept separate from the decision itself.
    rationale = [n for n in belief.current
                 if n.predicate in (Predicate.HAS_REASON, Predicate.HAS_TRADEOFF,
                                    Predicate.HAS_BENEFIT, Predicate.HAS_RISK)]
    if rationale:
        paragraphs.append(" ".join(f"On {subject}, {phrase(n)}" +
                                   ("" if phrase(n).endswith(".") else ".")
                                   for n in rationale[:3]))

    # 3. What it replaced. This is the half of the answer retrieval never gives.
    for node in belief.history:
        line = f"This replaced an earlier position: {phrase(node)}, {_evidence_clause(node)}."
        if node.retired_by_artifact_id:
            line += f" It was retired by artifact {node.retired_by_artifact_id[:16]}"
            if node.retirement_basis == "ingestion_order":
                line += ", though the ordering rests on ingestion order rather than dates"
            line += "."
        paragraphs.append(line)

    # 4. Structural facts that are not the decision.
    structural = [n for n in belief.current
                  if n.predicate in (Predicate.USES, Predicate.DEPENDS_ON,
                                     Predicate.CONTAINS, Predicate.REQUIRES,
                                     Predicate.PROHIBITS, Predicate.IMPORTS)]
    if structural:
        paragraphs.append("Related structure: " +
                          "; ".join(phrase(n) for n in structural[:5]) + ".")

    # 5. Anything memory could not settle. Never omitted to make the answer
    #    read better.
    if belief.conflicts:
        paragraphs.append(
            f"Memory holds {len(belief.conflicts)} unresolved contradiction(s) "
            f"touching this topic; it recorded the disagreement rather than "
            f"choosing between them."
        )

    if belief.identity and belief.identity.is_merged:
        others = ", ".join(belief.identity.alternate_labels)
        paragraphs.append(
            f"This answer treats {subject} and {others} as one concept, because "
            f"the project asserted they are the same thing."
        )

    caveats = [d for d in belief.diagnostics
               if "ingestion order" in d or "no timestamped" in d]
    if caveats:
        paragraphs.append("Caveat: " + " ".join(caveats))

    return "\n\n".join(paragraphs)
