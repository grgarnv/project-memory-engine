"""
MCP server.

The pilot interface. Exposes the read path as tools so the engine answers inside
whatever the team already uses, rather than asking people to learn a CLI.

Read-only by design, with one exception. `correct` is exposed because the
correction loop only works if disputing a fact is as easy as reading one - a
correction path that requires a terminal is a correction path nobody uses. It
writes an append-only correction artifact and cannot delete anything.

stdio JSON-RPC, no dependencies.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from memory_engine.apps import ComplianceEngine, brief
from memory_engine.correction import Correction, CorrectionError, apply_correction
from memory_engine.ontology import Predicate
from memory_engine.resolve import BeliefResolver, ProjectQueries, explain, render
from memory_engine.store import SQLiteProjectMemory

PROTOCOL_VERSION = "2024-11-05"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "ask_project",
        "description": "What does the project currently believe about a concept, "
                       "with the evidence behind it and what it replaced.",
        "inputSchema": {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
        },
    },
    {
        "name": "project_timeline",
        "description": "Everything recorded about a concept in chronological order, "
                       "including when positions were retired.",
        "inputSchema": {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
        },
    },
    {
        "name": "project_dependents",
        "description": "What currently relies on a concept - blast radius if it changes.",
        "inputSchema": {
            "type": "object",
            "properties": {"entity": {"type": "string"}},
            "required": ["entity"],
        },
    },
    {
        "name": "check_constraint",
        "description": "Check whether a proposed relationship violates a recorded "
                       "constraint. Absence of a rule is reported as unknown, not permission.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
    },
    {
        "name": "project_brief",
        "description": "Onboarding overview: current decisions, rules, what changed, "
                       "and what memory is unsure about.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "correct_fact",
        "description": "Record that a fact is wrong. Appends a correction artifact and "
                       "retires the fact; nothing is deleted and the history stays queryable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "string"},
                "author": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["fact_id", "author", "reason"],
        },
    },
]


def _all_facts(memory) -> list:
    rows = memory.conn.execute("SELECT id FROM facts").fetchall()
    return [memory.get_fact(r["id"]) for r in rows]


class MemoryMCPServer:
    def __init__(self, db_path: str):
        self.memory = SQLiteProjectMemory(db_path)

    def call(self, name: str, args: dict) -> str:
        if name == "ask_project":
            belief = BeliefResolver(self.memory).explain(args["entity"])
            return explain(belief) + "\n\n" + render(belief)

        if name == "project_timeline":
            entries = ProjectQueries(self.memory).timeline(args["entity"])
            if not entries:
                return f"Nothing recorded about {args['entity']!r}."
            return "\n".join(
                f"{e.when or 'undated':<12} {'+' if e.event == 'asserted' else '-'} {e.statement}"
                for e in entries
            )

        if name == "project_dependents":
            found = ProjectQueries(self.memory).dependents(args["entity"])
            if not found:
                return f"Nothing currently depends on {args['entity']!r}."
            return "\n".join(
                f"{d.label} ({d.predicate.value}) support={d.support}" for d in found
            )

        if name == "check_constraint":
            try:
                predicate = Predicate(args["predicate"])
            except ValueError:
                return f"Unknown predicate {args['predicate']!r}."
            report = ComplianceEngine(self.memory).check(
                [(args["subject"], predicate, args["object"])]
            )
            return report.summary()

        if name == "project_brief":
            return brief(self.memory, _all_facts(self.memory)).render()

        if name == "correct_fact":
            try:
                delta = apply_correction(self.memory, Correction(
                    fact_id=args["fact_id"], author=args["author"], reason=args["reason"],
                ))
            except CorrectionError as exc:
                return f"Could not record the correction: {exc}"
            return (
                f"Recorded. Fact {args['fact_id']} is retired on {args['author']}'s "
                f"authority and remains queryable as history. "
                f"{len(delta.supersessions)} supersession edge written."
            )

        return f"Unknown tool {name!r}."

    # -- JSON-RPC -----------------------------------------------------------

    def handle(self, request: dict) -> dict | None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "project-memory-engine", "version": "0.4.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            text = self.call(params.get("name", ""), params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": text}]}
        elif method in ("notifications/initialized", "notifications/cancelled"):
            return None
        else:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown method {method}"}}

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                response = self.handle(json.loads(line))
            except json.JSONDecodeError:
                continue
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    db = args[0] if args else "project.db"
    MemoryMCPServer(db).serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
