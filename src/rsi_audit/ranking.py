"""Does a leaderboard's order survive resampling its tasks?

Input is one score per (agent, task). The aggregate is recomputed two ways and, if published
values are given, must match them before anything else is said. Each adjacent pair in the
published order gets P(order holds) under a task bootstrap, cross-checked by a normal
approximation on the paired per-task differences.
"""
from __future__ import annotations

import csv
import math
import random

FRAGILE_BELOW = 0.80
ROBUST_AT = 0.95


def load(path):
    """{agent: {task: score}} from a CSV with columns agent, task, score."""
    table = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            a, t, s = row["agent"].strip(), row["task"].strip(), row["score"].strip()
            if t in table.setdefault(a, {}):
                raise ValueError("duplicate score for %s / %s" % (a, t))
            table[a][t] = float(s)
    return table


def _complete(table):
    tasks = sorted({t for scores in table.values() for t in scores})
    missing = ["%s/%s" % (a, t) for a in table for t in tasks if t not in table[a]]
    if missing:
        raise ValueError("every agent needs a score on every task; missing: %s" % ", ".join(missing[:10]))
    return tasks


def aggregate(values, how):
    """Two independent routes; raises if they disagree."""
    n = len(values)
    if how == "geomean":
        if min(values) <= 0:
            raise ValueError("geomean needs positive scores")
        r1 = math.exp(sum(math.log(v) for v in values) / n)
        r2 = math.prod(values) ** (1.0 / n)
    elif how == "mean":
        r1 = sum(values) / n
        r2 = math.fsum(values) / n
    else:
        raise ValueError("aggregate must be geomean or mean")
    if abs(r1 - r2) > 1e-9 * max(1.0, abs(r1)):
        raise ArithmeticError("aggregate routes disagree: %r vs %r" % (r1, r2))
    return r1


def analyse(table, how="geomean", order=None, published=None, top=6, resamples=10000, seed=0, tol=5e-4):
    tasks = _complete(table)
    n = len(tasks)
    if n < 2:
        raise ValueError("need at least 2 tasks")
    agg = {a: aggregate([table[a][t] for t in tasks], how) for a in table}

    check = []
    if published:
        for a, p in published.items():
            if a not in agg:
                raise ValueError("published agent %r has no scores" % a)
            check.append({"agent": a, "published": p, "recomputed": agg[a], "match": abs(agg[a] - p) < tol})
        if not all(c["match"] for c in check):
            return {"verdict": "STOP: RECOMPUTED AGGREGATES DO NOT MATCH THE PUBLISHED ONES",
                    "aggregate_check": check}

    order = list(order) if order else sorted(agg, key=agg.get, reverse=True)
    unknown = [a for a in order if a not in table]
    if unknown:
        raise ValueError("agents in the order with no scores: %s" % unknown)
    x = {a: [math.log(table[a][t]) if how == "geomean" else table[a][t] for t in tasks] for a in table}

    rng = random.Random(seed)
    draws = [[rng.randrange(n) for _ in range(n)] for _ in range(resamples)]

    pairs = []
    head = order[:top]
    for a, b in zip(head, head[1:]):
        d = [x[a][i] - x[b][i] for i in range(n)]
        hold = sum(1 for ix in draws if sum(d[i] for i in ix) > 0) / resamples
        m = sum(d) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in d) / (n - 1))
        normal = 0.5 * (1 + math.erf((m / (sd / math.sqrt(n))) / math.sqrt(2))) if sd > 0 else (1.0 if m > 0 else 0.0)
        pairs.append({"above": a, "below": b, "p_bootstrap": hold, "p_normal": normal,
                      "mc_se": math.sqrt(hold * (1 - hold) / resamples),
                      "wins": sum(v > 0 for v in d), "losses": sum(v < 0 for v in d), "ties": sum(v == 0 for v in d)})

    first = {}
    for ix in draws:
        g = {a: sum(x[a][i] for i in ix) for a in table}
        w = max(g, key=g.get)
        first[w] = first.get(w, 0) + 1
    loo = {}
    for j in range(n):
        g = {a: sum(x[a][i] for i in range(n) if i != j) for a in table}
        w = max(g, key=g.get)
        loo[w] = loo.get(w, 0) + 1

    worst = min((p["p_bootstrap"] for p in pairs), default=1.0)
    if worst < FRAGILE_BELOW:
        verdict = "FRAGILE"
    elif all(p["p_bootstrap"] >= ROBUST_AT for p in pairs):
        verdict = "ROBUST"
    else:
        verdict = "MIXED"
    return {
        "verdict": verdict,
        "tasks": n,
        "aggregate": how,
        "aggregates": agg,
        "aggregate_check": check,
        "pairs": pairs,
        "routes_agree": all(abs(p["p_bootstrap"] - p["p_normal"]) < 0.10 for p in pairs),
        "p_rank1": {k: v / resamples for k, v in sorted(first.items(), key=lambda kv: -kv[1])},
        "leave_one_task_out_rank1": loo,
        "note": "the task bootstrap ignores run-to-run noise; with one run per agent per task, FRAGILE is a "
                "lower bound on fragility and ROBUST does not certify the order",
    }


def report(r):
    out = []
    if r.get("aggregate_check"):
        out.append("Recomputed vs published %s:" % r.get("aggregate", "aggregate"))
        for c in r["aggregate_check"]:
            out.append("  %-24s published %.4f  recomputed %.4f  %s"
                       % (c["agent"], c["published"], c["recomputed"], "match" if c["match"] else "MISMATCH"))
    if r["verdict"].startswith("STOP"):
        out.append(r["verdict"])
        return "\n".join(out)
    out.append("Adjacent pairs (%d tasks, task bootstrap / normal approximation):" % r["tasks"])
    for p in r["pairs"]:
        out.append("  %-22s > %-22s  P=%.3f (+/-%.3f) / %.3f   per-task %d wins, %d losses, %d ties"
                   % (p["above"], p["below"], p["p_bootstrap"], p["mc_se"], p["p_normal"],
                      p["wins"], p["losses"], p["ties"]))
    out.append("P(rank 1): " + ", ".join("%s %.3f" % kv for kv in r["p_rank1"].items()))
    out.append("Leave-one-task-out rank 1: " + ", ".join("%s %d" % kv for kv in r["leave_one_task_out_rank1"].items()))
    out.append("Routes agree within 0.10: %s" % r["routes_agree"])
    out.append("VERDICT: %s  (FRAGILE if any adjacent pair P < %.2f; ROBUST if all >= %.2f)"
               % (r["verdict"], FRAGILE_BELOW, ROBUST_AT))
    out.append("Note: " + r["note"])
    return "\n".join(out)
