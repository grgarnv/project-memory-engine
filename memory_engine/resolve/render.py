"""
Rendering a ResolvedBelief.

Presentation only. Nothing here decides anything: if a line is not in the
resolved belief, it does not appear, and nothing is smoothed over or inferred
to make the output read better.
"""
from __future__ import annotations

from memory_engine.resolve.resolver import BeliefNode, ResolvedBelief


def _evidence_line(ev) -> str:
    when = ev.recorded_at or "undated"
    return (
        f"      {ev.artifact_type:<12} {when:<12} "
        f"weight={ev.weight:<6} artifact={ev.artifact_id[:20]}"
    )


def _node_block(node: BeliefNode, indent: str = "  ") -> list[str]:
    lines = [
        f"{indent}{node.subject_label} --{node.predicate.value}--> {node.object_label}",
        f"{indent}  support={node.support} across {node.evidence_count} artifact(s)"
        f"{'  last asserted ' + node.last_asserted if node.last_asserted else ''}",
    ]
    lines.extend(_evidence_line(ev) for ev in node.evidence)
    if node.retired_by_fact_id:
        lines.append(
            f"{indent}  retired by {node.retired_by_fact_id[:20]} "
            f"({node.retirement_reason}; basis={node.retirement_basis})"
        )
        if node.retired_by_artifact_id:
            lines.append(f"{indent}    via artifact {node.retired_by_artifact_id[:20]}")
    return lines


def render(belief: ResolvedBelief) -> str:
    lines: list[str] = [f"Q: what does the project believe about '{belief.query}'?", ""]

    if not belief.answered:
        lines.append("UNANSWERABLE FROM MEMORY")
        lines.extend(f"  ! {d}" for d in belief.diagnostics)
        return "\n".join(lines)

    if belief.current:
        lines.append("CURRENT")
        for node in belief.current:
            lines.extend(_node_block(node))
        lines.append("")

    if belief.history:
        lines.append("SUPERSEDED")
        for node in belief.history:
            lines.extend(_node_block(node))
        lines.append("")

    if belief.conflicts:
        lines.append("CONFLICTS")
        for c in belief.conflicts:
            lines.append(f"  {c.fact_a_id[:20]} <!> {c.fact_b_id[:20]} ({c.conflict_type})")
        lines.append("")

    if belief.diagnostics:
        lines.append("DIAGNOSTICS")
        lines.extend(f"  ! {d}" for d in belief.diagnostics)

    return "\n".join(lines).rstrip()
