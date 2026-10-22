"""Was the final number chosen on the set it is graded on, and how often was the gate re-rolled?

selection(): from a log of development evaluations (candidate, dataset, score), did the submission
come from comparing several candidates on the graded set itself?

luck(): from the number of record claims per run and the gate's own per-claim false-pass rate, how
many luck-only passes should be expected? Thresholds are in expected-pass units, so they carry over
to any rate.
"""
from __future__ import annotations

import csv

LUCK_TOP_MATERIAL = 0.1     # one top run expected to hold >= 0.1 luck-only passes
LUCK_TOTAL_MATERIAL = 1.0   # >= 1 expected luck-only pass across the study
LUCK_TOP_NEGLIGIBLE = 0.03
LUCK_TOTAL_NEGLIGIBLE = 0.3


def load_dev(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [{"candidate": r["candidate"].strip(), "dataset": r["dataset"].strip(), "score": float(r["score"])}
                for r in csv.DictReader(f)]


def selection(rows, graded, submitted):
    on_graded = [r for r in rows if r["dataset"] == graded]
    best = {}
    for r in on_graded:
        best[r["candidate"]] = max(best.get(r["candidate"], float("-inf")), r["score"])
    n_cand = len(best)
    out = {"graded_set": graded, "dev_evaluations_on_graded_set": len(on_graded),
           "distinct_candidates_on_graded_set": n_cand, "candidates": best, "submitted": submitted}
    if n_cand < 2:
        out["verdict"] = "NOT FOUND"
        return out
    if submitted not in best:
        raise ValueError("submitted candidate %r was never scored on %r; name one of %s"
                         % (submitted, graded, sorted(best)))
    top = max(best.values())
    out["submitted_score"] = best[submitted]
    out["best_score"] = top
    out["spread"] = top - min(best.values())
    out["verdict"] = ("SELECTION ON TEST" if best[submitted] >= top
                      else "GRADED-SET DEVELOPMENT, NOT ARGMAX")
    return out


def selection_report(r):
    out = ["Graded set: %s -- %d development evaluation(s), %d distinct candidate(s) scored on it."
           % (r["graded_set"], r["dev_evaluations_on_graded_set"], r["distinct_candidates_on_graded_set"])]
    for c, s in sorted(r["candidates"].items(), key=lambda kv: -kv[1]):
        out.append("  %-30s %.4f%s" % (c, s, "   <- submitted" if c == r["submitted"] else ""))
    out.append("VERDICT: %s" % r["verdict"])
    if r["verdict"] == "SELECTION ON TEST":
        out.append("The reported number is the best of several candidates compared on the graded tasks; it is "
                   "biased upward by an amount that grows with the number of candidates and their noise. "
                   "Re-score the submitted system on tasks it never saw.")
    elif r["verdict"].startswith("GRADED-SET"):
        out.append("The graded tasks were used during development, but the submission is not the best of them.")
    return "\n".join(out)


def luck(claims, rate, top=None):
    """claims: {run: n_claims}; top: runs whose records are headline results (default: all)."""
    top = list(top) if top else list(claims)
    exp = {k: v * rate for k, v in claims.items()}
    total = sum(exp.values())
    top_max = max(exp[k] for k in top)
    if top_max >= LUCK_TOP_MATERIAL or total >= LUCK_TOTAL_MATERIAL:
        verdict = "LUCK MATERIAL"
    elif top_max < LUCK_TOP_NEGLIGIBLE and total < LUCK_TOTAL_NEGLIGIBLE:
        verdict = "LUCK NEGLIGIBLE"
    else:
        verdict = "INCONCLUSIVE"
    return {"verdict": verdict, "rate": rate, "claims_total": sum(claims.values()),
            "expected_lucky_total": total, "expected_lucky_top_max": top_max, "per_run": exp}


def luck_report(r):
    return "\n".join([
        "Claims attempted: %d at a per-claim luck rate of %g." % (r["claims_total"], r["rate"]),
        "Expected luck-only passes: %.3f across the study; %.3f in the most-claimed headline run."
        % (r["expected_lucky_total"], r["expected_lucky_top_max"]),
        "VERDICT: %s  (MATERIAL if a headline run >= %.2f or total >= %.1f; NEGLIGIBLE if every headline run < %.2f "
        "and total < %.1f)" % (r["verdict"], LUCK_TOP_MATERIAL, LUCK_TOTAL_MATERIAL, LUCK_TOP_NEGLIGIBLE,
                               LUCK_TOTAL_NEGLIGIBLE),
        "Note: uses the claimed per-claim rate as given; a recipe sitting at the threshold passes by luck more often.",
    ])
