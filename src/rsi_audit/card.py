"""The claim card: what a self-improvement result needs before its number means anything.

Each item is answered yes / no / partial with evidence. An unanswered item is UNKNOWN, never a pass.
"""
from __future__ import annotations

import json

ITEMS = [
    ("matched_control", "A control arm that differs only in the claimed mechanism (same compute, same tasks): "
                        "e.g. random search, no-feedback reflection, or the fixed baseline harness run as long."),
    ("compute_matched", "Treatment and control spend the same compute, or the difference is reported and priced."),
    ("training_seeds", "Repeated independent TRAINING runs (evaluation repeats of one run do not count)."),
    ("intervals", "An uncertainty interval on the headline number and on every comparison it is used for."),
    ("held_out", "The final number is measured on tasks never used during development "
                 "(rsi-audit selection checks this from a development log)."),
    ("claims_attempted", "The number of candidates or record claims tried is reported, not only the ones that passed "
                         "(rsi-audit luck turns it into expected luck-only passes)."),
    ("gate_covers_scored_regime", "The correctness check exercises the regime that is scored -- same lengths, same "
                                  "code path, same serving setup. (RSI-Inference Bench: gate is short-context prefill; "
                                  "score is long decode.)"),
    ("cheats_scored_as_failures", "Runs that game the grader are detected and scored as failures, and how is stated."),
    ("grader_hidden", "The agent cannot read the grader's tests, answers or reference solution "
                      "(rsi-audit visibility checks this from the repository)."),
    ("ranking_resampled", "Any ranking is shown to survive resampling of tasks and runs "
                          "(rsi-audit ranking checks this from per-task scores)."),
    ("precommitted", "Tasks, answer keys and the grading rule were fixed and hashed before any run."),
    ("harness_disclosed", "The scaffold or harness around the model is published with the score; the same model "
                          "can move tens of points with the harness alone."),
]
ANSWERS = ("yes", "no", "partial")


def template():
    return {k: {"answer": "", "evidence": ""} for k, _ in ITEMS}


def score(filled):
    rows = []
    for key, text in ITEMS:
        entry = filled.get(key) or {}
        ans = str(entry.get("answer", "")).strip().lower()
        if ans not in ANSWERS:
            ans = "unknown"
        rows.append({"item": key, "requirement": text, "answer": ans, "evidence": entry.get("evidence", "")})
    extra = sorted(set(filled) - {k for k, _ in ITEMS} - {"claim"})
    met = sum(r["answer"] == "yes" for r in rows)
    return {"claim": filled.get("claim", ""), "rows": rows, "met": met, "of": len(ITEMS), "unrecognised": extra}


def report(r, markdown=False):
    if markdown:
        out = ["## Claim card: %s" % (r["claim"] or "(unnamed claim)"), "",
               "| Requirement | Answer | Evidence |", "|---|---|---|"]
        for x in r["rows"]:
            out.append("| `%s` | **%s** | %s |" % (x["item"], x["answer"].upper(), x["evidence"].replace("|", "\\|")))
        out += ["", "**%d of %d requirements met.** UNKNOWN counts as not met." % (r["met"], r["of"])]
    else:
        out = ["Claim: %s" % (r["claim"] or "(unnamed)")]
        for x in r["rows"]:
            out.append("  %-27s %-8s %s" % (x["item"], x["answer"].upper(), x["evidence"]))
        out.append("%d of %d requirements met (UNKNOWN counts as not met)." % (r["met"], r["of"]))
    if r["unrecognised"]:
        out.append("Unrecognised keys ignored: %s" % ", ".join(r["unrecognised"]))
    return "\n".join(out)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
