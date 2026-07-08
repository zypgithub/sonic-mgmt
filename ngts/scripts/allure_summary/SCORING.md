# Offline matcher scoring rubric

## Why a deterministic scorer

The AI agent is good at reading bug descriptions and weighing context.
It's also slow (3-5 seconds per failure), non-reproducible (same input
can produce slightly different verdicts), and expensive (one LLM call per
failure). For the bulk of failures, none of that judgment is needed: the
test name appears verbatim in some Redmine bug's `tests[]` field, or the
bug's `error_pattern` is a substring of the test's actual assertion text.
Those cases want a millisecond-fast, reproducible answer with no token
budget.

The offline matcher in `ngts/scripts/allure_summary/bug_marker.py`
provides exactly that. It runs inline during the pytest conftest finalize
step. For every failing test it walks the baseline, scores each candidate
bug against the failure, and attaches the single highest-scoring bug to
the test result. Same inputs, same outputs, every run.

> **Why this matters:** the offline matcher is the floor. The AI agent
> only handles failures the offline matcher could not. If you can shape
> the bug's `tests[]` field or its `error_patterns[]` so the offline
> matcher picks it deterministically, do that - the AI agent's tokens
> are better spent on the harder cases.

## What you'll learn

- The 100 / 80 / 60 / 30 / 20 / +5 rubric and what each tier represents.
- Why log_analyzer test-name matches are demoted when the syslog pattern
  does not also appear in the failure's `statusMessage`.
- Why log_analyzer + trace-only matches are excluded entirely.
- A worked walkthrough on a real failure with three candidates.
- The knobs you can turn when the rubric is wrong, and the calibration
  tool that tells you whether your tuning helped.

## The rubric

| Score | Signal | Worked example |
|-------|--------|----------------|
| **100** | Test name appears in `bug.tests[]` exactly (suffix `[NVUE]` or `[OpenApi]` allowed) AND `bug.kind != "log_analyzer"`. | Failure `test_system_remarkable_logs_storm[NVUE]` matches bug `#4978152` whose `tests` list contains `test_system_remarkable_logs_storm`. Score: 100. |
| **80**  | Bug lists a test-name prefix and the failure adds an underscore suffix AND `bug.kind != "log_analyzer"`. | Bug `tests=[test_system_issu]`, failure `test_system_issu_positive_basic_flow`. Same family, slight drift. Score: 80. |
| **60**  | One of `bug.error_patterns[]` is a substring of the failure's `statusMessage` (the assertion text). | Bug `#4931671` has `error_patterns=["events table reached maximum"]`. Failure's statusMessage: `AssertionError: events table reached maximum capacity`. Score: 60. |
| **DROP** | Test-name match (exact or prefix) for a `log_analyzer`-kind bug whose `error_pattern` does NOT also hit `statusMessage`. | Bug `#4918063` kind=log_analyzer lists `test_show_fae_platform_cpo` in tests[] (auto-extracted from a teardown syslog scan), but its `error_pattern` `WARNING kernel: sxd_kernel...` never appears in the failure's `AssertionError: ELS dictionary mismatch`. The candidate is dropped entirely - test-name auto-extraction is too noisy for log_analyzer tickets to attribute on by itself. |
| **20**  | An `error_pattern` matched in `statusTrace` only, not in `statusMessage`. | Same bug, but the phrase only shows up in the traceback (loganalyzer teardown), not in the AssertionError. Score: 20 (weak). Dropped entirely when `bug.kind == "log_analyzer"`. |
| **+5**  | Tie-breaker bonus when `bug.kind == "feature"`. | Two bugs both score 60 on the same failure. The one whose `kind` is `feature` wins (60+5 vs 60). |

The matcher walks every bug in the baseline, computes the highest
applicable score for that bug, and picks the single (bug, score) pair
with the maximum score. Ties go to the first match found - which, with
the +5 feature bonus, biases toward feature bugs over log_analyzer ones.

> **Why this matters:** test-name in `bug.tests[]` is the ceiling at 100
> (105 with feature bonus). Error-pattern tiers max out at 65. If you
> want a binding to be deterministic, the path is to get the test name
> into the bug, not to tune `error_patterns[]`.

## Why log_analyzer + trace-only is dropped

Before scoring, one rule short-circuits a candidate entirely:

> If `bug.kind == "log_analyzer"` AND the `error_pattern` matched in
> `statusTrace` only (not in `statusMessage`), **drop the candidate**.

Here's why. The pytest `loganalyzer` plugin runs at every test's teardown.
It scans syslog for ERR lines and appends anything new to the test's
status output. Real bug fires during teardown - say, a `Redmine
#4915280: nvued: ERR cannot find config key X` - and that exact ERR line
shows up in the `statusTrace` of every test that ran in the same minute,
even tests that have nothing to do with the nvued config key.

Without the exclusion, the matcher saw the pattern in the trace and
attached `#4915280` to dozens of unrelated tests. With the exclusion,
log_analyzer bugs are only eligible when their pattern appears in
`statusMessage` - that's the "the assertion explicitly cites the syslog
ERR" case, which is legitimate (60 points).

A concrete instance: `test_system_remarkable_logs_error` was getting
two log_analyzer bugs attached even though the actual assertion was about
a missing log file. The trace happened to contain unrelated nvued and
syncd-ibv01 ERR lines because loganalyzer scraped them. After the
exclusion, that test correctly lands in "no known bug" (the failure is
genuinely new) instead of in the wrong bucket.

## Walkthrough: one failure, three candidates

The matcher's input on this failure:

```
test:           test_system_remarkable_logs_storm[NVUE]
statusMessage:  AssertionError: storm_prints_log.1.gz file does not exist
                in the path /var/log/remarkable_logs_1
statusTrace:    ... ERR nvued: cannot find config key X
                ... ERR syncd-ibv01#SDK: timeout on poll
                ... (more loganalyzer scrapes)
```

The pre-filter surfaces three candidates from the baseline:

| Bug | Status | Kind | What it has |
|-----|--------|------|-------------|
| `#4978152` | Rejected | feature | `tests=[test_system_remarkable_logs_storm]` |
| `#4915280` | Open | log_analyzer | `error_patterns=["ERR nvued: cannot find config key X"]` |
| `#4996367` | Open | log_analyzer | `error_patterns=["ERR syncd-ibv01#SDK: timeout on poll"]` |

The matcher scores each:

- **`#4978152`** - test name matches `bug.tests[]` exactly. Base score
  100. Bonus +5 because `kind == feature`. Final: **105**.
- **`#4915280`** - `error_pattern` matched in `statusTrace` only,
  `bug.kind == log_analyzer`. **Dropped by the hard exclusion.**
- **`#4996367`** - same as above. **Dropped.**

Winner: `#4978152`. The matcher attaches it with the rejected sentinel
(`[KB#4978152] Rejected bug: ...`) and the `rejected_bug` tag. The two
log_analyzer bugs that would have piled on under the old "match any
pattern" matcher don't show up. The triager sees one clean attribution.

## Tie-breaking with the feature bonus

The +5 bonus matters only when two candidates would otherwise tie. The
common case:

| Bug | Tier | Kind | Score |
|-----|------|------|-------|
| `#X` | 60 (error_pattern in statusMessage) | log_analyzer | 60 |
| `#Y` | 60 (error_pattern in statusMessage) | feature | 65 |

`#Y` wins. The intuition: a feature bug typically describes a specific
product defect ("events table overflow when N >= 1000"), while a
log_analyzer bug is an auto-filed wrapper around a syslog line. When
both legitimately match the assertion, the specific-defect bug is the
better attribution.

If you ever want to bias more strongly, raise the bonus from 5 to 20 -
no log_analyzer bug will ever beat a feature bug at the same tier.

## Calibration: keeping the rubric and AI in sync

When you tune the rubric (raise a tier, drop the log_analyzer exclusion,
add a new signal), you want to know whether the change agrees with the
AI agent's judgment - the AI is the slower but more flexible reasoner.

`validate_mappings_with_llm.py` does exactly that. Point it at a recent
report URL; it runs the offline matcher's pick on each failure, asks
the configured LLM for its independent verdict on the same failure (same candidates),
and prints the agreement rate.

```bash
INFERENCE_HUB_API_KEY=$INFERENCE_HUB_API_KEY \
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/validate_mappings_with_llm.py \
  "https://allure.nvidia.com/.../projects/<source>/reports/130/index.html"
```

Typical output:

```
Failures analyzed:        28
Offline pick agrees:      22 (78.6%)
LLM picks but offline -:   3
Offline picks but LLM -:   2
Both pick, different:      1
```

Use this before merging a rubric change: capture the agreement rate on
two reports, change the knob, re-run, and confirm agreement went up or
held steady. If a rubric tweak drives agreement down, the AI is telling
you the rubric got worse.

## When the rubric is wrong: tuning knobs

All knobs are in
`ngts/scripts/allure_summary/bug_marker.py:attach_baseline_to_failed_results`,
roughly 20 lines of code.

| If you observe | Try changing |
|----------------|--------------|
| The matcher refuses to bind a bug whose `error_pattern` clearly matches the assertion text, because some other bug also lists the test name with a wrong attribution. | Raise the `60` tier (error_pattern in statusMessage) toward `100`. Error-pattern matches become as strong as test-name matches. |
| The matcher picks an `error_pattern` match when a different bug actually owns the test (`tests[]` was missing the name). | Lower the `60` to `40` or `30`. Forces test-name to win in mixed cases - then fix the bug's `tests[]` to be the real answer. |
| log_analyzer bugs still win when a feature bug should. | Raise the feature bonus from `+5` to `+20`. The feature bug wins decisively at the same tier. |
| Triagers want to see both a feature bug and its log_analyzer twin on a failure. | Replace the `max(...)` pick with a "top-2 keep" - allow two attributions if both clear a threshold. Defeats the "one bug per failure" rule but is a real product call. |
| A class of failures has a strong signal in `fullName` (e.g. parametrize id) that the current tiers miss. | Add a new tier (say, 70 = `error_pattern` in `fullName`). Slot it between 80 and 60. |
| You're tempted to drop the log_analyzer + trace-only exclusion. | Don't. We did this on accident once and re-introduced the over-attribution bug it was designed to fix. If you do drop it, run `validate_mappings_with_llm.py` immediately to confirm it didn't tank agreement. |

After any tuning change, re-run the calibration script on a recent
report and confirm agreement with the LLM did not drop.

## Where this rubric does NOT apply

- **The AI agent** (`ai_attribute_report.py`) - uses its own reasoning
  via the LLM plus `ai_feedback.json` patterns. It also picks at most
  one bug per failure, but the decision logic is a sequential checklist,
  not a numeric score.
- **The deprecated pytest-marker hook** - used to apply
  `@pytest.mark.bug` literally, no scoring at all. Not currently wired.

## Inspecting why a particular pick won

The matcher does not yet log per-candidate scores. If you need to debug
a single failure's attribution during triage, the cleanest local route
is a temporary print:

```python
from ngts.scripts.allure_summary.bug_marker import (
    attach_baseline_to_failed_results, load_baseline,
)
# Inside attach_baseline_to_failed_results, add a temporary
#   print({c['redmine_id']: score for c, score in candidate_scores})
# right before the max(...) call. Run pytest with a single failing test
# and inspect stdout.
```

A `--debug-scores` flag on the matcher is a possible future addition.
For AI-attributed runs you already have the agent's full reasoning in
`audit[*].verdict.reason` in the session JSON.

## What's next

- `README.md` - the architecture, how the offline matcher and AI agent
  share the baseline, the cron flow, how triagers read attributed
  reports.
- `AI_FEEDBACK_GUIDE.md` - the AI agent's side. Read it before adding a
  feedback rule that duplicates an offline-matcher behavior.
- `ai_attribute_report.py --help` - all flags including `--variant` for
  A/B-testing rule changes.
