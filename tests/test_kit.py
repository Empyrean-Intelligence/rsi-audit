"""Known-answer tests. Real cases reproduce verdicts from published audits; planted cases must go red.

Run: python tests/test_kit.py
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from rsi_audit import card, ranking, selection, visibility  # noqa: E402

FAILS = []


def check(name, cond, got=""):
    print("%-4s %s %s" % ("ok" if cond else "FAIL", name, got))
    if not cond:
        FAILS.append(name)


# ---- ranking ----
rng = random.Random(1)
tasks = ["t%d" % i for i in range(27)]
dominant = {"A": {t: 1.5 + rng.random() * 0.1 for t in tasks}, "B": {t: 1.2 + rng.random() * 0.1 for t in tasks}}
r = ranking.analyse(dominant)
check("ranking: A better on every task -> ROBUST", r["verdict"] == "ROBUST", r["verdict"])

rng = random.Random(2)
coin = {"A": {t: 1.0 + rng.random() for t in tasks}, "B": {t: 1.0 + rng.random() for t in tasks}}
r = ranking.analyse(coin, order=["A", "B"])
check("ranking: two noise agents -> not ROBUST", r["verdict"] != "ROBUST", "%s P=%.3f" % (r["verdict"], r["pairs"][0]["p_bootstrap"]))
tied = {"A": {t: 1.3 for t in tasks}, "B": {t: 1.3 for t in tasks}}
r = ranking.analyse(tied, order=["A", "B"])
check("ranking: identical agents -> FRAGILE (P=0, ties never count as holding)", r["verdict"] == "FRAGILE", r["verdict"])

r = ranking.analyse(dominant, published={"A": 9.99, "B": 1.25})
check("ranking: published aggregate that does not match -> STOP", r["verdict"].startswith("STOP"), r["verdict"])
try:
    ranking.analyse({"A": {"t1": 1.0, "t2": 1.1}, "B": {"t1": 1.0}})
    check("ranking: missing score raises", False)
except ValueError:
    check("ranking: missing score raises", True)

# ---- selection: three candidates compared on the graded set, best submitted; a fourth on a dev set ----
picked = [{"candidate": "cand_a", "dataset": "graded", "score": 0.61},
          {"candidate": "cand_b", "dataset": "graded", "score": 0.66},
          {"candidate": "cand_c", "dataset": "graded", "score": 0.72},
          {"candidate": "cand_d", "dataset": "dev", "score": 0.50}]
r = selection.selection(picked, "graded", "cand_c")
check("selection: best of 3 on the graded set submitted -> SELECTION ON TEST", r["verdict"] == "SELECTION ON TEST",
      "%s n_cand=%d" % (r["verdict"], r["distinct_candidates_on_graded_set"]))
notbest = [{"candidate": c, "dataset": "graded", "score": s}
           for c, s in [("cand_a", 0.80), ("cand_b", 0.80), ("cand_c", 0.78), ("final", 0.77)]]
r = selection.selection(notbest, "graded", "final")
check("selection: graded set used, submission not the best -> GRADED-SET DEVELOPMENT, NOT ARGMAX",
      r["verdict"] == "GRADED-SET DEVELOPMENT, NOT ARGMAX", r["verdict"])
disjoint = [{"candidate": c, "dataset": "dev_split", "score": s} for c, s in [("a", 0.5), ("b", 0.6)]]
r = selection.selection(disjoint, "test_split", "b")
check("selection: development only on a disjoint set -> NOT FOUND", r["verdict"] == "NOT FOUND", r["verdict"])

# ---- luck: in expected-pass units, so the thresholds carry to any rate ----
r = selection.luck({"top": 50, "rest": 400 - 50}, 0.001, ["top"])
check("luck: 400 claims, top run 50 -> INCONCLUSIVE, expected 0.400",
      r["verdict"] == "INCONCLUSIVE" and abs(r["expected_lucky_total"] - 0.4) < 1e-9,
      "%s %.3f" % (r["verdict"], r["expected_lucky_total"]))
r = selection.luck({"top": 50, "rest": 1200 - 50}, 0.001, ["top"])
check("luck: 1,200 claims -> LUCK MATERIAL", r["verdict"] == "LUCK MATERIAL", r["verdict"])
r = selection.luck({"top": 5, "rest": 15}, 0.001, ["top"])
check("luck: 20 claims -> LUCK NEGLIGIBLE", r["verdict"] == "LUCK NEGLIGIBLE", r["verdict"])

# ---- visibility: planted leak in a directory, and the resolve.sh false positive ----
with tempfile.TemporaryDirectory() as root:
    def put(rel, text):
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    put("tasks/t1/tests/hidden/case1.json", '{"expected": 42}')
    put("tasks/t1/tests/check.py", "def check(): pass\n")
    put("tasks/t1/tests/lock/resolve.sh", "echo resolve\n")
    put("tasks/t1/environment/scripts/check.py", "def check(): pass\n")
    put("tasks/t1/environment/lock/resolve.sh", "echo resolve\n")
    put("tasks/t2/tests/hidden/case1.json", '{"expected": 7}')
    put("tasks/t2/environment/notes.md", "nothing\n")
    files = visibility.files_from_dir(root)
    r = visibility.scan(files, ["tests/*", "solution/*"], ["environment/*"], tasks="tasks/*")
    check("visibility: shared harness only -> NO LEAK FOUND (resolve.sh is not a solution)",
          r["verdict"] == "NO LEAK FOUND" and len(r["shared"]) == 2, "%s shared=%d" % (r["verdict"], len(r["shared"])))
    put("tasks/t1/environment/data/case1.json", '{"expected": 42}')
    r = visibility.scan(visibility.files_from_dir(root), ["tests/*", "solution/*"], ["environment/*"], tasks="tasks/*")
    check("visibility: planted copy of a hidden test -> LEAK", r["verdict"] == "LEAK" and len(r["leaks"]) == 1,
          "%s leaks=%d" % (r["verdict"], len(r["leaks"])))
    put("tasks/t2/environment/copy.json", '{"expected": 42}')
    r = visibility.scan(visibility.files_from_dir(root), ["tests/*"], ["environment/*"], tasks="tasks/*")
    check("visibility: content from ANOTHER task is not a leak of this one", len(r["leaks"]) == 1, "leaks=%d" % len(r["leaks"]))
    try:
        visibility.scan(files, ["graders/*"], ["environment/*"], tasks="tasks/*")
        check("visibility: globs matching no grader file raise", False)
    except ValueError:
        check("visibility: globs matching no grader file raise", True)

# ---- card ----
r = card.score({"claim": "x", "matched_control": {"answer": "yes"}, "intervals": {"answer": "maybe"}})
check("card: unanswered and invalid answers are UNKNOWN, not met", r["met"] == 1 and
      sum(x["answer"] == "unknown" for x in r["rows"]) == len(card.ITEMS) - 1, "met=%d" % r["met"])

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
