# rsi-audit

**Check a self-improvement or agent-leaderboard claim from its public artefacts.**

A self-improving system is only as good as its ability to tell a real improvement from a fooled check.
`rsi-audit` is the verification layer we use on our own self-improvement work at Empyrean Intelligence,
released so anyone can apply it to theirs.

"Our agent improved itself from 0.32 to 0.98" and "model X ranks third" are numbers that look the same
whether or not they mean anything. `rsi-audit` runs the checks that separate the two, on a laptop, with no
model and no API key: from per-task scores, a development log, a repository, or a count of attempts.

```
pip install "git+https://github.com/Empyrean-Intelligence/rsi-audit"   # PyPI release coming
rsi-audit ranking scores.csv --published published.csv
rsi-audit visibility path/to/benchmark --tasks 'tasks/*' --grader 'tests/*' --visible 'environment/*'
rsi-audit selection devlog.csv --graded graded_test --submitted harness_v2
rsi-audit luck --total 400 --top-max 50 --rate 0.001
rsi-audit card filled_card.json --markdown
```

Each check was built from an audit of a published self-improvement claim (write-ups follow once their
authors have had the chance to reply), and each goes red on a planted copy of the defect it looks for
(`tests/`).

## The checks

| Check | Question | Input | Verdicts |
|---|---|---|---|
| `ranking` | Does the leaderboard order survive resampling the tasks? | `agent,task,score` CSV | ROBUST / MIXED / FRAGILE |
| `visibility` | Can the agent read the grader's tests, answers or reference solution? | benchmark directory or git revision | NO LEAK FOUND / LEAK |
| `selection` | Was the reported system picked by comparing candidates on the graded tasks? | `candidate,dataset,score` log | NOT FOUND / GRADED-SET DEVELOPMENT, NOT ARGMAX / SELECTION ON TEST |
| `luck` | How many record claims could have passed the gate by luck alone? | claims per run and the gate's own false-pass rate | NEGLIGIBLE / INCONCLUSIVE / MATERIAL |
| `card` | What does the claim still owe? | a filled card (`rsi-audit card --template`) | n of 12 requirements met |

Exit code 3 means a check found the defect it looks for; 2 means it refused to analyse (for example,
recomputed aggregates that do not match the published ones); 0 otherwise.

### `ranking`

One score per agent per task. The aggregate (geometric mean by default, or `--aggregate mean`) is computed
two independent ways; with `--published`, it must match the published values before anything else is
reported. Then, for each adjacent pair in the top six, the share of 10,000 task resamples in which the
published order still holds, cross-checked against a normal approximation on the paired per-task
differences, plus the probability of rank 1 and a leave-one-task-out check. FRAGILE if any adjacent pair
holds less than 80% of the time; ROBUST if every pair holds at least 95%. Resampling tasks ignores
run-to-run noise, so with one run per task FRAGILE understates the problem and ROBUST does not certify
the order.

### `visibility`

Compares file *content* (git blob hashes) between the grader's paths and the paths the agent can see,
within each task. Identical content in a path that looks like a held-out test, answer key or reference
solution (`hidden/`, `solution/`, `expected/`, `gold/`, `known_good*`, `solve.sh`, ...) is a LEAK; any other
match is listed as SHARED, usually harness code given on purpose, worth a read. `--rev` reads a git
revision straight from the object store, which works where a checkout fails (long Windows paths) and never
runs anything from the benchmark. NO LEAK FOUND is not a proof of isolation: a leak through a network path,
a mount the globs miss or a re-encoded copy is not seen.

### `selection`

From every development evaluation (`candidate,dataset,score`): how many distinct candidates were scored on
the graded set, and whether the submission is the best of them. A number chosen that way is biased upward,
by more as the candidates multiply and the scores get noisier. The fix is to re-score the submitted system
on tasks it never saw.

### `luck`

A record gate ("8 seeds must all beat the threshold; passing by luck is one in a thousand") protects one
claim. Re-submitted hundreds of times, it protects much less. Given claims per run and the gate's own
per-claim luck rate, `luck` reports the expected number of luck-only passes: MATERIAL if a headline run
reaches 0.1 or the whole study reaches 1, NEGLIGIBLE below 0.03 and 0.3. It uses the stated rate as given;
a recipe sitting right at the threshold passes by luck more often.

### `card`

Twelve requirements a self-improvement number needs, each answered yes / no / partial with evidence:
matched control, matched compute, repeated training runs, intervals, held-out final evaluation, attempts
reported, a correctness gate that covers the regime actually scored, cheats scored as failures, a hidden
grader, a resampled ranking, a pre-committed task set, a disclosed harness. An unanswered item counts as
not met. `rsi-audit card --template` prints an empty card; `examples/card_example.json` is a filled one.

## What it does not do

- It does not run anyone's benchmark, model or agent. Every check reads artefacts that are already public.
- It does not say anyone cheated. It says what the published evidence can and cannot support.
- Whether a correctness gate covers the scored regime is a card item, not an automated check: it needs a
  person to read the grader.

## Tests

```
python tests/test_kit.py                          # known answers and planted defects
```

## License

MIT
