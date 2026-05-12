# AI agent feedback guide

## Why feedback matters

The AI agent (`ai_attribute_report.py`) is not omniscient. It sees one
failure at a time - a stack trace, a `statusMessage`, a `statusTrace`, and
up to 10 candidate bugs from the baseline - and has to pick one or refuse.
Out of the box, without `ai_feedback.json`, it gets a particular class of
failure wrong over and over: it over-attributes teardown noise.

Here's the failure mode that motivated the feedback file in the first
place. The `loganalyzer` pytest plugin scans syslog at every test's
teardown, picks up any ERR lines that happened to land in the window, and
appends them to the test's `statusTrace`. Because of that, an `error_pattern`
from a log_analyzer bug (say, `Redmine #4915280: ERR nvued: cannot find
config key X`) ends up in the trace of almost every test that ran near a
real bug. The LLM, looking at one failure and one candidate, sees the
pattern, sees that the bug is "open", and picks it. Result: every fatal-mode
test in the regression got blamed on `#4915280`.

The feedback file taught the agent the corrected rule: for log_analyzer
bugs, require the `error_pattern` to appear in `statusMessage`
(the test's actual assertion text), not just `statusTrace`
(the loganalyzer's syslog scrape). That single rule, expressed once as a
`pattern_lesson`, fixed dozens of wrong attributions.

## What you'll learn

- The two channels in `ai_feedback.json` and when to use each.
- The audit / edit loop: run the agent, read the session JSON, write a
  rule, re-run, compare.
- DOs and DONTs for `pattern_lessons` - the ones that bit us.
- What the weekly cache audit does, and why "refusal" is a feature.

## What the feedback file looks like

`ai_feedback.json` has two channels. Both are folded into the agent's
system prompt every run; the LLM sees them once per failure alongside
that failure's specific data.

### Channel 1: `system_prompt_addendum`

A single free-text block of rules appended to the LLM's instructions. Use
this for general policies that apply across all failures.

```json
{
  "system_prompt_addendum": "Rule 1: For bugs whose subject starts with [log_analyzer], require the error_pattern to appear in the failure's statusMessage, not only in statusTrace. The statusTrace often contains unrelated teardown noise from the loganalyzer plugin.\n\nRule 2: When two candidates have near-identical subjects, prefer the lower-numbered bug ID (it's the earlier-filed, generally more authoritative report)."
}
```

Good rules are specific, bounded, and actionable. Bad rules are broad
("be skeptical of weak candidates"), subjective ("use your best
judgment"), or self-contradictory.

### Channel 2: `pattern_lessons`

A list of structured failure-mode lessons. Each entry teaches the agent
to recognize a recurring shape of mistake and apply the right heuristic.

```json
{
  "pattern_lessons": [
    {
      "pattern": "Software-stack defect rejected on platform mismatch",
      "trigger": "Candidate bug describes a software subsystem (gNMI, NVUE CLI, syslog, ZTP, telemetry, configmgrd, nv-umf, ACL CRUD, tech-support) AND its setup_filters omits the current setup.",
      "common_mistake": "Refusing the attribution because setup_filters does not list this platform.",
      "correct_heuristic": "Platform alignment is NOT required for software-stack defects. Apply the attribution if the failure symptom matches the bug subject, regardless of setup_filters. Reserve strict platform alignment for hardware/PHY/ASIC defects.",
      "illustration": "Failure: test_some_api_throttle on mamba. Candidate: bug #ABCDEFG (subject: 'gNMI rate-limit returns 503'), setup_filters=[crocodile]. Verdict: attribute, conf=0.85. Reason: gNMI is software-stack; platform shouldn't matter."
    }
  ]
}
```

The fields:

- `pattern` - one-line name. Shows up in the prompt as the lesson header.
- `trigger` - the abstract shape the agent should recognize. No specific
  test names, no specific bug IDs.
- `common_mistake` - what the agent would naively do, and why it's wrong.
- `correct_heuristic` - what to do instead.
- `illustration` - one anonymized worked example. `test_some_api_throttle`
  and `#ABCDEFG` are placeholders, not real cases - the LLM uses them as
  few-shot anchors without conflating them with ground truth.

### How the agent uses the file

```
ai_feedback.json
       |
       v
  build_system_prompt()
       |
       |  1. Start from LLM_SYSTEM_BASE (the fixed core rules in the script)
       |  2. Append system_prompt_addendum
       |  3. Format each pattern_lesson as a numbered block
       v
  +---------------------------------------------+
  | system message  ->  LLM (temperature 0.1)       |
  | user message    ->  one failure + candidates    |
  +----------------------+----------------------+
                         |
                         v
              {redmine_id, confidence, reason}
```

Loaded at agent startup, applied per-failure, no state survives between
runs. The feedback file IS the long-term memory.

## The audit / edit loop

The cycle for improving the agent has five steps.

### 1. Run the agent on a recent report

```bash
INFERENCE_HUB_API_KEY=$INFERENCE_HUB_API_KEY \
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/ai_attribute_report.py \
  "https://allure.nvidia.com/.../projects/<source>/reports/130/index.html" \
  --loose \
  --feedback /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_feedback.json \
  --variant test-myfix
```

The `--variant` flag tags this run's session JSON so you can compare it
to a baseline run later.

### 2. Inspect the session JSON

```bash
ls -lt /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_session_*_test-myfix_*.json | head -1
jq '.ambiguities_for_review' \
  /auto/sw_system_project/NVOS_INFRA/bug_attribution/ai_session_<source>_test-myfix_<ts>.json
```

### 3. Focus on `ambiguities_for_review`

The session JSON groups uncertain decisions into three buckets:

- `low_confidence_pick` - the agent picked a bug but its confidence was
  below 0.7. Often correct, but worth checking.
- `deliberate_refusal` - the agent saw candidates and refused with
  confidence >= 0.3. It actively decided "none of these." This is where
  most rule problems show up.
- `weak_refusal` - the agent refused but its confidence in refusing was
  also low. Usually a pre-filter problem (bad candidates).

### 4. Edit `ai_feedback.json`

For each pattern you see across multiple failures, decide:

- General policy (applies regardless of test) -> add a sentence to
  `system_prompt_addendum`.
- Recurring shape with a clear trigger -> add a `pattern_lesson`.
- Specific (test, bug) pairing that should always bind -> NOT here. Two
  paths, in order of preference:
    1. Edit the Redmine bug's subject or description to include the test
       name. The nightly baseline extractor picks it up and both engines
       see it. Single source of truth, scales naturally.
    2. Add an entry to `known_bugs_mappings.json` (system_type +
       test_name + error_msg substring -> redmine_id). Hand-curated,
       immediate effect, useful when you need a strict (setup, test,
       error) match the description-scanner cannot express. Treat as the
       override channel, not the default.

### 5. Re-run and compare

Same command, same `--variant`. Diff the new session JSON against the
previous one:

- Picks went up, refusals went down, wrong IDs stayed flat - good.
- Picks went up but wrong IDs also went up - rule is too aggressive.
- Refusals dropped across the board - over-restrictive rule got loosened
  correctly, or the rule was too narrow.

## Writing good `pattern_lessons`

DO:

- **Abstract the trigger.** "Software-stack defect on a platform-mismatched
  setup" generalizes; "the gnmi rate-limit test on mamba" does not.
- **Use placeholder illustrations.** `test_some_api_throttle`, `#ABCDEFG`.
  Anchors for the LLM without polluting it with real ground truth.
- **Order by precedence.** Check 1 fires first, Check 2 second. If you
  have a hard exclusion (like the log_analyzer + trace-only rule), put it
  near the top.
- **Phrase as "when X, do Y."** Concrete trigger, concrete action.
- **Keep <= 12 active lessons.** The agent silently drops the extras to
  bound the prompt size. If you have 12, retiring an old one is part of
  adding a new one.

DON'T:

- **Don't paste real test names or bug IDs.** Those are ground truth and
  they belong in Redmine. A `pattern_lesson` referring to "Redmine
  #4915280" cannot transfer to any other case.
- **Don't write blanket-skepticism rules.** "Be skeptical of weak
  candidates" sounds wise. In practice it makes the LLM over-refuse and
  kills recall. Selective skepticism (by class - log_analyzer, hardware,
  weak token overlap) is fine; blanket is not.
- **Don't add a lesson the matcher already handles correctly.** The LLM
  treats every lesson as a pattern to repeat. If you add a rule "when
  test X fails on platform Y, attribute bug Z," the LLM may try to apply
  the shape of that rule to unrelated cases.
- **Don't expand the candidate pool via feedback.** Feedback cannot
  conjure a candidate the pre-filter didn't surface. If the right bug
  never reached the LLM, the fix is in `pick_candidates()` or in the
  bug's Redmine `tests[]` extraction.

## The weekly cache audit

```bash
PYTHONPATH=$(pwd):$(pwd)/../devts ./.venv/bin/python \
  ngts/scripts/allure_summary/audit_known_pairings.py
```

Runs Monday mornings after `sync_known_bugs_cron.sh`. The job walks
`ai_known_pairings.json` and drops every entry whose bug status is now
Closed, Resolved, or Verified. Rejected bugs are kept on purpose -
"this failure mode is the known-rejected bug #N" is still useful triage
signal in a regression meeting.

Typical drop count is under 10 per week. If it's higher, something has
landed a wave of fixes and that's normal. If it's zero for weeks, suspect
the audit job is not running and check the cron.

## When the agent refuses

A refusal is not a failure - it's a feature.

The agent will refuse to commit a cache entry when its confidence is
below 0.95. That threshold is deliberately conservative. The cache is
read fast-path by every subsequent run, so a wrong entry survives and
multiplies until someone notices. Refusing protects future runs from a
single bad call.

If you see refusals clustering on a real bug - i.e. you know
`test_foo_bar` should attribute to `#1234567` and the agent keeps
refusing - the fix is **not** to twist a rule until the agent attributes.
The fix is to edit `#1234567` in Redmine: put `test_foo_bar` in the
subject or description. The baseline extractor will pick it up overnight,
the offline matcher will score it at 100, and the AI agent never has to
make the judgment call.

> **Why this matters:** every feedback rule you add applies to every
> failure the agent sees, forever. Specific pairings belong in the source
> of truth, which is Redmine. Reserve the feedback file for genuinely
> abstract patterns.

## What the agent does NOT learn between runs

- No fine-tuning. Each invocation is a fresh prompt.
- No automatic feedback collection. You write the lessons.
- Past verdicts are not in-context. Only `system_prompt_addendum` and
  active `pattern_lessons` survive between runs.

If you want richer state (per-bug confidence thresholds, allow-lists),
that's a script change in `ai_attribute_report.py`. The feedback file is
for prompt-level instructions only.

## What's next

- `README.md` - the architecture, the two engines, the cron flow, how to
  read an attributed report.
- `SCORING.md` - the deterministic offline matcher's rubric. If you find
  yourself writing a feedback rule that duplicates the offline matcher's
  behavior, read SCORING.md first.
- `ai_attribute_report.py:LLM_SYSTEM_BASE` - the fixed core prompt your
  feedback gets appended to. Read it to know what baseline rules you are
  overriding or refining.
