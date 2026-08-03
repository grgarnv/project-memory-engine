"""
Answerability check.

Before deploying this on any repository, find out whether that repository's
decisions are written down at all. The engine cannot recover what was never
recorded, and no amount of extraction work changes that.

Three commands:

    python3 scripts/answerability.py sample  <repo> [-n 30]
        Randomly sample decision documents. Random matters - picking the
        well-written ones measures your best documents, not your project.

    python3 scripts/answerability.py sheet   <repo> --questions questions.txt
        Build a scoring sheet. You fill in one bucket per question, by hand.
        This step is human judgement and the script will not do it for you.

    python3 scripts/answerability.py score   sheet.csv
        Read the filled sheet and tell you whether to proceed.

The three buckets:

    1  written and localised   the answer sits in one document
    2  written but scattered   recoverable only by reading several and joining
    3  not written down        lives in someone's head, a call, or a DM

Bucket 2 is the one this engine exists for: a person answers it in twenty
minutes of reading, memory answers it instantly. Bucket 1 is served fine by
grep. Bucket 3 is the ceiling on anything you build.
"""
from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
from pathlib import Path

# Where projects usually keep decision records. Checked in order; all matches
# are used, so a repo with both ADRs and RFCs contributes both.
DECISION_DIRS = (
    "docs/adr", "docs/adrs", "docs/architecture-decisions", "docs/decisions",
    "adr", "adrs", "architecture/decisions", "doc/adr",
    "rfcs", "docs/rfcs", "text", "keps", "designs", "docs/design",
    "proposals", "docs/proposals",
)

BUCKETS = {
    "1": "written and localised",
    "2": "written but scattered",
    "3": "not written down",
}


def find_decision_dirs(repo: Path) -> list[Path]:
    found = [repo / d for d in DECISION_DIRS if (repo / d).is_dir()]
    if found:
        return found
    # Fall back to any directory with several numbered markdown files, which is
    # what an ADR folder looks like regardless of what it is called.
    candidates = []
    for path in repo.rglob("*.md"):
        parent = path.parent
        if parent in candidates or ".git" in path.parts:
            continue
        numbered = [p for p in parent.glob("*.md")
                    if any(c.isdigit() for c in p.stem[:4])]
        if len(numbered) >= 5:
            candidates.append(parent)
    return candidates


def cmd_sample(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    dirs = find_decision_dirs(repo)
    if not dirs:
        print("No decision-record directory found. Looked for:")
        print("  " + ", ".join(DECISION_DIRS))
        print("\nThis repo may not keep written decisions. That is itself a result.")
        return 1

    print(f"Found {len(dirs)} candidate director(ies):")
    for d in dirs:
        print(f"  {d.relative_to(repo)}  ({len(list(d.glob('*.md')))} files)")

    docs = [p for d in dirs for p in d.glob("*.md")
            if p.stem.lower() not in ("readme", "index", "template")]
    if not docs:
        print("\nNo documents found.")
        return 1

    random.seed(args.seed)
    picked = random.sample(docs, min(args.n, len(docs)))

    out = Path(args.out)
    out.write_text("\n".join(str(p.relative_to(repo)) for p in sorted(picked)) + "\n")
    print(f"\nSampled {len(picked)} of {len(docs)} documents -> {out}")
    print(f"Seed {args.seed}. Same seed reproduces this sample, so the result is checkable.")
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    questions = [q.strip() for q in Path(args.questions).read_text().splitlines()
                 if q.strip() and not q.startswith("#")]
    if not questions:
        print(f"{args.questions} has no questions in it.")
        return 1

    out = Path(args.out)
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question", "bucket", "documents_needed", "notes"])
        for question in questions:
            writer.writerow([question, "", "", ""])

    print(f"Wrote {len(questions)} rows -> {out}")
    print("\nFill in the `bucket` column by hand, one of:")
    for key, label in BUCKETS.items():
        print(f"  {key}  {label}")
    print("\n`documents_needed` = how many documents you had to read to answer it.")
    print("Answer each question yourself from the sampled documents. If you cannot")
    print("find it in them, it is a 3 - do not credit what you happen to know.")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    rows = list(csv.DictReader(Path(args.sheet).open()))
    scored = [r for r in rows if (r.get("bucket") or "").strip() in BUCKETS]

    if not scored:
        print("Nothing scored yet. Fill in the `bucket` column first.")
        return 1
    if len(scored) < len(rows):
        print(f"note: {len(rows) - len(scored)} of {len(rows)} rows are unscored\n")

    counts = {key: 0 for key in BUCKETS}
    for row in scored:
        counts[row["bucket"].strip()] += 1
    total = len(scored)

    print(f"scored {total} question(s)\n")
    for key, label in BUCKETS.items():
        share = counts[key] / total
        bar = "#" * round(share * 40)
        print(f"  {key}  {label:<24} {counts[key]:>3}  {share:>4.0%}  {bar}")

    localised = counts["1"] / total
    scattered = counts["2"] / total
    missing = counts["3"] / total

    print()
    if missing > 0.5:
        print("STOP. More than half these decisions were never written down.")
        print("No compiler recovers what does not exist. The ceiling here is")
        print(f"{1 - missing:.0%} before extraction quality enters the picture.")
        print("This is a finding about documentation practice, not about the engine.")
        return 2

    if scattered < 0.2:
        print("MARGINAL. Most answers sit in a single document, so grep and a")
        print("good search box already serve them. The engine earns its keep on")
        print("bucket 2 - questions that need several documents joined together -")
        print(f"and that is only {scattered:.0%} here.")
        return 3

    print("PROCEED.")
    print(f"{scattered:.0%} of questions need several documents joined - that is the")
    print("work this engine does and a person currently does by hand.")
    print(f"{localised:.0%} are single-document lookups you get for free alongside.")
    if missing:
        print(f"{missing:.0%} are unrecoverable; treat that as the accuracy ceiling.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="randomly sample decision documents")
    p_sample.add_argument("repo")
    p_sample.add_argument("-n", type=int, default=30)
    p_sample.add_argument("--seed", type=int, default=1)
    p_sample.add_argument("--out", default="sampled_docs.txt")
    p_sample.set_defaults(func=cmd_sample)

    p_sheet = sub.add_parser("sheet", help="build a scoring sheet from your questions")
    p_sheet.add_argument("--questions", required=True)
    p_sheet.add_argument("--out", default="answerability.csv")
    p_sheet.set_defaults(func=cmd_sheet)

    p_score = sub.add_parser("score", help="read a filled sheet and decide")
    p_score.add_argument("sheet")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
