"""rsi-audit: check a self-improvement or agent-leaderboard claim from its public artefacts."""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import card, ranking, selection, visibility

EXIT_FLAG = 3  # a check found the defect it looks for


def _dump(obj, path):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)


def cmd_ranking(a):
    table = ranking.load(a.scores)
    published = None
    if a.published:
        with open(a.published, newline="", encoding="utf-8") as f:
            published = {r["agent"].strip(): float(r["value"]) for r in csv.DictReader(f)}
    order = [s.strip() for s in a.order.split(",")] if a.order else None
    r = ranking.analyse(table, how=a.aggregate, order=order, published=published, top=a.top,
                        resamples=a.resamples, seed=a.seed)
    print(ranking.report(r))
    _dump(r, a.json)
    return 2 if r["verdict"].startswith("STOP") else (EXIT_FLAG if r["verdict"] == "FRAGILE" else 0)


def cmd_visibility(a):
    files = visibility.files_from_git(a.path, a.rev) if a.rev else visibility.files_from_dir(a.path)
    r = visibility.scan(files, a.grader, a.visible, tasks=a.tasks)
    print(visibility.report(r, show_shared=a.show))
    _dump(r, a.json)
    return EXIT_FLAG if r["leaks"] else 0


def cmd_selection(a):
    r = selection.selection(selection.load_dev(a.devlog), a.graded, a.submitted)
    print(selection.selection_report(r))
    _dump(r, a.json)
    return EXIT_FLAG if r["verdict"] == "SELECTION ON TEST" else 0


def cmd_luck(a):
    if a.claims:
        with open(a.claims, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        claims = {r["run"].strip(): int(r["claims"]) for r in rows}
        top = [r["run"].strip() for r in rows if str(r.get("headline", "")).strip().lower() in ("1", "yes", "true")]
    else:
        if a.total is None or a.top_max is None:
            sys.exit("give --claims FILE, or both --total and --top-max")
        claims = {"headline": a.top_max, "rest": a.total - a.top_max}
        top = ["headline"]
    r = selection.luck(claims, a.rate, top or None)
    print(selection.luck_report(r))
    _dump(r, a.json)
    return EXIT_FLAG if r["verdict"] == "LUCK MATERIAL" else 0


def cmd_card(a):
    if a.template:
        print(json.dumps({"claim": "", **card.template()}, indent=1))
        return 0
    r = card.score(card.load(a.file))
    print(card.report(r, markdown=a.markdown))
    _dump(r, a.json)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="rsi-audit", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ranking", help="does a leaderboard order survive resampling its tasks?")
    s.add_argument("scores", help="CSV: agent,task,score (one row per agent per task)")
    s.add_argument("--aggregate", choices=["geomean", "mean"], default="geomean")
    s.add_argument("--published", help="CSV: agent,value -- recomputed aggregates must match these first")
    s.add_argument("--order", help="published order, comma-separated (default: recomputed order)")
    s.add_argument("--top", type=int, default=6)
    s.add_argument("--resamples", type=int, default=10000)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--json")
    s.set_defaults(fn=cmd_ranking)

    s = sub.add_parser("visibility", help="can the agent see the grader's tests or answers?")
    s.add_argument("path", help="benchmark directory, or a git repository with --rev")
    s.add_argument("--rev", help="read this git revision from the object store instead of the working tree")
    s.add_argument("--tasks", help="glob for task directories, e.g. 'tasks/*' (compare within each task)")
    s.add_argument("--grader", action="append", required=True, help="glob of grader files (repeatable)")
    s.add_argument("--visible", action="append", required=True, help="glob of agent-visible files (repeatable)")
    s.add_argument("--show", type=int, default=5)
    s.add_argument("--json")
    s.set_defaults(fn=cmd_visibility)

    s = sub.add_parser("selection", help="was the submission chosen on the graded set?")
    s.add_argument("devlog", help="CSV: candidate,dataset,score (every development evaluation)")
    s.add_argument("--graded", required=True, help="name of the graded dataset as it appears in the log")
    s.add_argument("--submitted", required=True, help="the candidate that was submitted")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_selection)

    s = sub.add_parser("luck", help="how many record claims could pass by luck?")
    s.add_argument("--claims", help="CSV: run,claims[,headline]")
    s.add_argument("--total", type=int, help="total claims (without --claims)")
    s.add_argument("--top-max", type=int, help="claims in the most-claimed headline run (without --claims)")
    s.add_argument("--rate", type=float, required=True, help="the gate's per-claim luck-only pass rate")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_luck)

    s = sub.add_parser("card", help="fill and score the claim card")
    s.add_argument("file", nargs="?", help="filled card JSON")
    s.add_argument("--template", action="store_true", help="print an empty card")
    s.add_argument("--markdown", action="store_true")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_card)

    a = p.parse_args(argv)
    if a.cmd == "card" and not a.template and not a.file:
        p.error("card needs a FILE or --template")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
