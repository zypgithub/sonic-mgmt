# NVOS bug-to-failure attribution

## Why this exists

When the regression meeting opens an Allure report, the first question is
always the same: "is this failure a new bug, or is it the one we already
filed last Tuesday?" Answering that by memory or wiki-grep does not scale -
a report can have 30 failures, half of them recurrences, and the regression
window is 45 minutes. This system answers the question automatically: every
failed test in a published report carries a clear sentinel ("Known bug
#4978152", "Rejected bug #...", or "No known bug") plus a clickable link
into Redmine.

## What you'll learn

After reading this doc you will be able to:

- Explain how the offline matcher and the AI agent split the work, and why
  we need both.
- Find every file the system reads or writes, and the cron job that owns it.
- Read an attributed Allure report from a triager's seat - what each tag
  and category means.
- Teach the system about a new (test, bug) pairing in one place: the
  Redmine ticket itself.
- Run any piece of the pipeline manually when cron or MARS is broken.

The companion docs go deeper on the two engines: `SCORING.md` for the
offline matcher's rubric, `AI_FEEDBACK_GUIDE.md` for tuning the AI agent.

## The two engines

There are two attribution engines. They share the same baseline of open
Redmine bugs; they differ in cost, speed, and the kind of failure they
can handle.

```
                    Redmine (nightly sync, query 36102)
                                    |
                                    v
                         known_bugs_baseline.json
                          (~1100 open + rejected bugs)
                                    |
                  +-----------------+-----------------+
                  |                                   |
                  v                                   v
        Offline matcher                       AI agent
   ngts/scripts/allure_summary/         ngts/scripts/allure_summary/
        bug_marker.py                      ai_attribute_report.py
                  |                                   |
   Deterministic rubric                 LLM via Inference Hub
   100 / 80 / 60 / 20 / +5              Feedback rules + cache
                  |                                   |
   Runs inline at pytest                Runs after report upload,
   conftest hook time.                  re-renders to <source>-ai-mapped
                  |                                   |
                  v                                   v
      Allure result XML carries        Sandbox Allure project with
      bug-link + sentinel              the same data plus AI picks
```

**Why two?** Roughly 70 percent of failures resolve from a test name that
appears verbatim in a Redmine bug's `tests[]` field, or from an
`error_pattern` substring that hits the assertion text. For those the
offline matcher is the right tool: deterministic, runs in milliseconds, no
LLM tokens, identical answers every run. The AI agent picks up the
remainder - failures where you have to read the bug description, weigh
platform context, and decide whether a software-stack defect filed on
Crocodile applies to a Black Mamba run.

> **Why this matters:** the offline matcher is the cheap, reproducible
> floor. The AI agent is the expensive, judgment-driven ceiling. If you
> see the AI re-deriving an answer the offline matcher should already
> know, look at SCORING.md - probably the bug needs the test name in its
> `tests[]` field.

## Where everything lives

There are two locations: a shared install directory that cron and MARS
read from, and the repo, which holds source and a recovery copy of the
shell wrappers.

### Shared install (`/auto/sw_system_project/NVOS_INFRA/bug_attribution/`)

This is the canonical install. The cron job and the MARS post-step both
invoke scripts from here.

| File | Owned by | Purpose |
|------|----------|---------|
| `known_bugs_baseline.json` | nightly cron | Snapshot of currently-open Redmine bugs (saved query 36102). Source of truth for both engines. |
| `ai_known_pairings.json` | AI agent | Cache of high-confidence (test, bug) pairings the agent committed to. Read fast-path, written on conf >= 0.95. |
| `ai_feedback.json` | you | Heuristic rules and `pattern_lessons` the AI agent folds into its system prompt. The only file a maintainer edits by hand. |
| `ai_session_<project>_<variant>_<ts>.json` | AI agent | Per-run audit log: every candidate seen, every verdict, every `ambiguities_for_review` flag. |
| `sync_known_bugs_cron.sh` | nightly cron | Wrapper around `sync_known_bugs.py` with rotation and sanity checks. |
| `ai_attribute_nightly.sh` | MARS post-step | Wrapper that reads the just-uploaded Allure URL for a setup and runs the AI agent. |

### Repo (`ngts/scripts/allure_summary/`)

The Python sources for both engines. The two shell wrappers also have a
**recovery copy** here (`sync_known_bugs_cron.sh`, `ai_attribute_nightly.sh`)
so you can re-deploy the shared install from a clean checkout if it gets
corrupted. The shared copy is what runs in production.

| File | Purpose |
|------|---------|
| `ai_attribute_report.py` | The AI agent. `--help` lists all flags. |
| `sync_known_bugs.py` | Pulls open + rejected bugs from Redmine, atomically writes `known_bugs_baseline.json`. |
| `audit_known_pairings.py` | Weekly cache prune. Drops entries whose Redmine bug is Closed / Resolved / Verified. |
| `validate_mappings_with_llm.py` | Calibration: runs offline rubric vs LLM on the same failures, prints agreement. |
| `sync_known_bugs_cron.sh` | Recovery copy of the cron wrapper. |
| `ai_attribute_nightly.sh` | Recovery copy of the MARS wrapper. |

The conftest-hook side of the offline matcher lives in
`bug_marker.py` alongside the other allure_summary sources, and is invoked
from `ngts/conftest.py` at collection time and session-finish time. It runs
inside the pytest process; SCORING.md documents exactly what it does.

## The nightly flow

In time order, on a normal day:

1. **02:30 UTC** - `sync_known_bugs_cron.sh` runs. Pulls Redmine query
   36102, scans every bug's subject + description for pytest test names,
   writes `known_bugs_baseline.json` atomically. Takes about 30 seconds for
   ~1100 bugs (open + last-90-days Rejected).
2. **02:32 UTC** - `audit_known_pairings.py` runs. Walks the AI cache,
   drops any entry whose bug status is now Closed / Resolved / Verified.
   Rejected entries stay - "this is the bug, and it was rejected" is still
   useful triage signal.
3. **All day** - regression jobs run. The offline matcher attaches its
   single best bug to each failing test as part of the conftest finalize
   step. The failing test's `statusMessage` gets a `[KB#NNNN]` prefix and
   tags like `known_bug` or `rejected_bug` show up in Allure.
4. **End of each regression** - MARS executes the "Generate final Allure
   report" step, uploads the report, then runs `ai_attribute_nightly.sh
   <setup>`. The AI agent picks up failures the offline matcher could not
   attribute (or that had ambiguous candidates), re-renders the report to
   a `<source>-ai-mapped` sandbox project with its picks, and writes an
   `ai_session_*.json` to the shared dir for audit.
5. **Mondays** - same audit job, plus a manual eyeball on the prior week's
   sessions to spot any systematic AI mistakes worth turning into a
   `pattern_lesson`.

## Reading an attributed report

Open any Allure report from a regression run. On a failing test you will
see, in order of where you'll find them:

- **The failure message itself** (top of the test view) starts with a
  sentinel:
  - `[KB#4978152] Known bug: ...` - offline matcher attached a non-rejected,
    non-AI bug.
  - `[KB#4978152] Rejected bug: ...` - matched a Redmine bug whose status
    is Rejected. Often still useful: "we know about this, we decided not
    to fix it."
  - `[AI#4915280] ...` - AI-agent attribution. Only appears in the
    `<source>-ai-mapped` sandbox project, not the original.
  - `[NO KB] No known bug` - neither engine had a high-confidence pick.
    Treat as a new failure.
- **Tags** on the test - `known_bug`, `rejected_bug`, or `ai_attributed`.
  Tags are filterable in the Allure UI and they back the dashboard
  categories.
- **categories.json buckets** - the dashboard groups failures into
  "Known bugs", "Rejected bugs", "AI-attributed", and "Failures without a
  known bug." Triagers usually start in the last bucket.
- **A bug link** - clicking the sentinel jumps to the Redmine issue.

## Teaching the system about a new bug

This is the only manual step a developer needs to know.

**To bind a failing test to a Redmine bug:** edit the bug's **subject** or
**description** and add one or both of the following lines:

- `Affected tests: <test_a>, <test_b>` -- every `test_*` token in this line
  goes into `bug.tests[]`. The offline matcher scores 100 when one of those
  names appears verbatim in the failing test.
- `Error pattern: <verbatim phrase>` -- the phrase after the colon goes
  into `bug.error_patterns[]`. The offline matcher scores 60 when that
  phrase appears as a literal substring of the failure's `statusMessage`.

Either line alone is enough to attribute a failure deterministically.
**Comments and journal entries are NOT scanned** -- the convention only
works when the lines are in the description (or subject).

### Worked example

Suppose `test_system_events_maximum` is failing on every regression and
Redmine #4931671 is the bug tracking it, but the bug's description only
talks about "events table overflow under maximum load." The matcher will
not bind them until the test name appears in the bug.

Edit the bug's description and add either or both of these lines:

```
Affected tests: test_system_events_maximum, test_system_events_overflow
Error pattern: events table reached maximum capacity
```

Save. On the next 02:30 sync (or after running `sync_known_bugs.py --live`
manually) the baseline will pick both up:
- `bug.tests[]` gets every `test_*` token from the `Affected tests:` line
  -> deterministic score 100 when the failing test name appears verbatim.
- `bug.error_patterns[]` gets the `Error pattern:` phrase verbatim ->
  deterministic score 60 when the phrase appears as a substring of the
  failure's `statusMessage`.

Either line alone is enough to attribute the next matching failure
deterministically. Use both when you want belt-and-suspenders coverage:
the test-name line catches the test by identity, the error pattern catches
the same failure mode in OTHER tests that happen to hit it.

A few notes on naming:

- The bare test name is enough. The matcher also handles
  `[NVUE]` / `[OpenApi]` suffix variants - if the bug says
  `test_system_events_maximum`, both `test_system_events_maximum[NVUE]`
  and `test_system_events_maximum[OpenApi]` will match.
- The `Error pattern:` phrase is matched as a **literal substring** (case
  sensitive). Pick a distinctive fragment that you know appears verbatim
  in the failure's `statusMessage` - do NOT use wildcards (`*`, `.*`), and
  avoid generic boilerplate like `AssertionError:`. Good: a unique noun
  phrase from the assertion text. Bad: a regex with metacharacters.
- The extractor reads **subject + description only**. Comments and journal
  entries are ignored. If you write "this affects test_foo" in a Redmine
  comment, the matcher will not see it.
- A bug can list multiple tests. Add them on separate lines or
  comma-separated; the regex picks up every `test_*` token.
- A bug can list multiple error patterns. Add one `Error pattern:` line
  per pattern; each becomes its own substring rule.
- `bm`/`croc`/`taipan` are treated as the same XDR family for setup
  filtering - a bug filed against any one is eligible to attribute
  failures on the others (LLM Check 3 still rejects PHY/transceiver
  defects that genuinely are platform-specific).

### Override channel: `known_bugs_mappings.json`

For the rare case where the Redmine description cannot express the
pairing precisely (e.g. you want to bind a bug only when a specific
`system_type` and `error_msg` substring both match), the system also
consults a hand-curated mapping file at
`/auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_mappings.json`.
The shape is:

```json
{
  "mappings": [
    {
      "system_type": "mamba",
      "test_name": "test_upload_log_files",
      "error_msg": "ExceptionGroup: 1 sub-steps failed:",
      "redmine_id": 4572303,
      "subject": "[log_analyzer]| ERR nvued: ..."
    }
  ]
}
```

Both engines consult this file in addition to the Redmine baseline. The
match is a strict AND over `system_type` alias + exact `test_name` +
`error_msg` substring. Use this when you need precision the Redmine
text-scan cannot give you; otherwise prefer the Redmine path so the
pairing scales without a maintainer editing JSON.

## Running things manually

All commands assume CWD is your sonic-mgmt checkout. Substitute your own
path for the example below.

### Refresh the baseline from Redmine

```bash
REDMINE_API_TOKEN=$REDMINE_API_TOKEN \
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/sync_known_bugs.py --live
```

Atomic write to `/auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_baseline.json`.
Safe to re-run any time. Sanity-check:

```bash
jq '._meta' /auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_baseline.json
```

You should see a recent `fetched_at` and a `ticket_count` near 1100.

### Run the AI agent on one report

Variant F is the production setting: loose pre-filter plus the curated
feedback file. Replace the URL with a concrete numeric report ID; the
agent does not accept `/reports/latest/`.

```bash
INFERENCE_HUB_API_KEY=$INFERENCE_HUB_API_KEY \
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/ai_attribute_report.py \
  "https://allure.nvidia.com/.../projects/<source>/reports/130/index.html" \
  --loose \
  --feedback /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_feedback.json \
  --variant manual
```

Two outputs:

- A re-rendered sandbox Allure project named `<source>-ai-mapped` with the
  AI's picks rendered as bug links.
- A session JSON in the shared dir named
  `ai_session_<source>_manual_<ts>.json`. Look at `ambiguities_for_review`
  to see where the agent was uncertain.

### Audit the AI cache

```bash
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/audit_known_pairings.py
```

Drops cache entries whose Redmine status is Closed / Resolved / Verified.
Add `--dry-run` to preview without writing. Typical weekly drop count is
under 10.

### Health check

```bash
ls -lh /auto/sw_system_project/NVOS_INFRA/bug_attribution/

jq '._meta.fetched_at, ._meta.ticket_count' \
  /auto/sw_system_project/NVOS_INFRA/bug_attribution/known_bugs_baseline.json

jq '._meta.updated_at, ._meta.last_audit, (.pairings | length)' \
  /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_known_pairings.json

ls -lt /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_session_*.json | head -5
```

## When the agent gets it wrong

There's a short decision tree:

1. **One-off wrong attribution on a single test.** Ignore it. The agent
   picks 5-7 bugs per report on average; isolated mistakes wash out and
   are not worth a feedback rule.
2. **A whole class of failures keeps getting the same wrong attribution.**
   That's a `pattern_lesson` opportunity. Open the agent's session JSON,
   look at the failures in question, write a transferable rule (no test
   names, no bug IDs - those go in Redmine). See AI_FEEDBACK_GUIDE.md.
3. **The right bug exists in Redmine but the agent never picked it.** Two
   sub-cases. If the bug wasn't in the candidate list, the bug needs the
   test name in its subject or description so the baseline extractor will
   surface it. If the bug was a candidate but the LLM refused it, that's a
   feedback issue - read the `reason` field in the session JSON and refine
   the relevant rule.

> **Why this matters:** the feedback file teaches the agent how to reason
> about cases it has never seen. It does not teach specific pairings.
> Specific pairings live in Redmine, where the bug's owner controls them.

## What's next

- `SCORING.md` - the offline matcher's rubric: when test-name beats
  error_pattern, why log_analyzer + trace-only is excluded, how to tune
  the knobs.
- `AI_FEEDBACK_GUIDE.md` - the AI agent's feedback schema, the audit /
  edit loop, the anti-patterns we learned the hard way.
- `ngts/scripts/allure_summary/ai_attribute_report.py --help` - every flag
  the agent accepts, including the variants we use for A/B testing rule
  changes.
- `validate_mappings_with_llm.py` - calibration tool: runs offline picks
  and LLM picks on the same failures, prints agreement. Use this when you
  want to evolve the offline rubric without disturbing AI behavior.
