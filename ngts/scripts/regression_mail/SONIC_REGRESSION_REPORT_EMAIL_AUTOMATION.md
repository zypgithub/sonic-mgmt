# SONiC Regression Report Email Automation

This document defines the public command-line, input, and output contract for
the SONiC regression mail generator. Implementation details may change, but
automation jobs may rely on the behavior documented here.

## Command

Run the tool from a checked-out `sonic-mgmt` worktree:

```bash
python -m ngts.scripts.regression_mail \
  --excel <collected-results.xlsx> \
  --version <SONIC_VERSION> \
  --to <recipient> [--to <recipient> ...] \
  [--cc <recipient> ...]
```

Install the tool's Python dependency in the execution environment first:

```bash
python -m pip install -r ngts/scripts/regression_mail/requirements.txt
```

The command always generates the internal-review message and sends it
immediately through SMTP. There is no audience selector, render mode, Outlook
draft mode, or local `.eml` output.

## Arguments

`--excel PATH`

- Path to the collected regression result workbook.
- The workbook is read-only input and is never modified in place.
- The generated message contains a copy of the workbook with an
`internal comments` column added.

`--version SONIC_VERSION`

- Full SONiC image version to report.
- The supplied version is authoritative when the workbook contains multiple
versions.
- Only Excel rows whose normalized `os_version` matches this value are used.
- If no Excel row matches, the command sends a degraded message whose
generation-error section explains that no rows matched; it does not fabricate
report rows.

`--to ADDRESS`

- Primary recipient.
- Repeat the option to provide multiple recipients.
- At least one `--to` is required.

`--cc ADDRESS`

- Carbon-copy recipient; default is none.
- Repeat the option to provide multiple recipients.

These are the only command-line options. Repository, collection, live-service,
model, Jenkins, SSH, and SMTP settings use the defaults documented below.

## Recipient validation

The following are errors:

```text
no --to argument
an invalid --to or --cc address
```

## Data sources

Each report section has one authoritative source:

1. Image hash and sonic-buildimage branch: `RC_STATUS.md` for `--version`.
2. sonic-mgmt public hash: automatically resolved from the local release
  history and public GitHub history.
3. NvidiaTestData DB version: required `--version`.
4. Coverage and pass rate: regression dashboard APIs.
5. HWSKU and topology: selected rows in the input Excel workbook.
6. Failure Analysis: Excel failures enriched with dashboard engineer
  `analysis`; `Internal Comments` keeps the full result and `Comments` is its
   sanitized form.
7. Skipped tests: Excel skipped rows, with condition and reason confirmed
  against the matching sonic-mgmt source.
  The final folded mapping is also written to `skips.json` beside the input
  workbook.
8. GitHub issues affecting coverage: GitHub issue URLs found in skipped-row
  Excel `message` values.
9. Internally detected error messages: live SONIC - Design LogAnalyzer bug
  search performed synchronously by the mail command.
10. Additional image PRs: the `RC_STATUS.md` operation table.
11. Additional sonic-mgmt PRs: result produced by a synchronous
   `sonic_github_pr_report` execution and validated against the selected Git
   history.

## Excel input

The workbook must contain a result sheet with these columns:

```text
session_id
mars_key_id
testbed
test name
result
message
topology
host
asic
platform
hwsku
os_version
sanitized_testname
```

Column matching is case-sensitive. Additional columns are preserved.
Supported result values are `pass`, `fail`, and `skipped`, compared
case-insensitively.

Excel `message` is the JUnit `<skipped message>` projection, not a complete
runtime skip trace. The workbook also discards the JUnit skipped `type`, so a
pytest `xfail` may be indistinguishable from a true skip. Original JUnit XML,
the test-time sonic-mgmt Git SHA, pytest command line, and loaded conditional
mark files are used when available; the tool never infers missing runtime
facts from current source alone.

Failure records are joined to regression-report records by:

```text
Excel: session_id + mars_key_id + test name/sanitized_testname
API:   sessionId + keyId + name
```

Matching is best effort, but Excel is authoritative. The tool tries exact
and normalized keys only within the same image version. Every unmatched
Excel row remains in the result with empty analysis and empty `internal comments`; an unmatched API row is never substituted. A partial match rate
does not fail the command.

The input workbook may contain multiple image versions. Statistics, hardware
rows, failures, skipped tests, and the enriched attachment are filtered to
the required `--version`. An optional service prefix such as `SONiC.` is
normalized, but release train, RC number, hash, and suffix must otherwise
match exactly.

The tool never assigns an API analysis from another image version.

The workbook is also the only source for the hardware report table. The tool
groups rows by unique `(hwsku, topology)` pairs. `ReportId` is left blank.
There is no metadata YAML input.

## Regression-report inputs

The tool uses:

```text
GET /api/collections
GET /api/collections/:name?rows=1
GET /api/failure-analysis
GET /api/snapshot-summary?version=<SONIC_VERSION>
GET /api/coverage?version=<SONIC_VERSION>
```

The API base defaults to
`https://regression-report.mec01-asgard.nvidia.com`. The collection is always
derived from `--version` and must resolve to exactly one current
collection.

For records available in the current engineer overlay,
`recordKey = "mars-" + collection_record.id` joins the collection record to
the engineer analysis.

Coverage is read from `coverage.totals.coverage`. Pass rate is calculated
from snapshot groups as `sum(passed) / (sum(passed) + sum(failed))`; skipped
and `rmSkipped` records are excluded from the denominator. Dashboard queries
use `--version`. Only current dashboard versions are supported; historical
versions whose dashboard summary is empty are outside the initial
implementation scope.

Engineer `analysis` is the only human-analysis source for the base
`internal comments` value. A non-empty `analysis` is accepted regardless of
`done`. If `analysis` is empty, the base value remains empty: `verdict`,
`exception`, and Excel `message` are not promoted into a diagnosis.

Different non-empty engineer analyses in the same folded group are
de-duplicated and concatenated; none are silently discarded.

## Synchronous Redmine review

During every invocation, the mail command uses OpenCode and the configured
Redmine MCP to query these projects live:

```text
sonic-verification  (SONiC - Verification)
sonic-design        (SONIC - Design)
```

Failure-review candidates from both projects are fetched with their current
status, description, custom fields, relations, and journals. They are matched
against image version, test, setup, platform/HWSKU, normalized failure, and
journal evidence during the same process that generates the email. Complete
matching references and analysis are written to `Internal Comments`;
`Comments` remains concise and Redmine-free for later reuse.

There is no scheduled Redmine producer, pre-generated Redmine snapshot, or
stale-cache fallback. A live Redmine/MCP failure marks the affected section
unavailable and is included in the generated message. A successful live query
with no matching ticket is not an error.

### Err msgs detected internally

This section uses a separate deterministic live search restricted to:

```text
project: SONIC - Design (sonic-design)
tracker: Bug SW
author: LogAnalyzer User
status: open OR Won't Fix
updated_on: on or after the current branch search cutoff
```

These filters are applied by Redmine before ticket bodies or journals are
downloaded. The cutoff is a conservative lower bound derived from the current
branch's merge-base commit time because Git does not record branch creation
time. It may include older candidates but must not be later than the actual
branch creation. The `[log_analyzer]` subject prefix is corroborating evidence,
not a required pre-filter; the exact author and structured LogAnalyzer content
remain authoritative.

The current branch is the SONiC image branch derived from `--version`; for
example, `SONiC.202605_RC.70-...` resolves to `202605_RC`. A LogAnalyzer bug is
included only when both of these conditions hold:

1. The bug was opened/detected on the current branch, as shown by its initial
   description or `Detected In Version` field; or the bug was opened on a
   different branch but a later journal comment explicitly records a
   reproduction on the current branch.
2. Its current Redmine status is in the open-status category, or its normalized
   status is exactly `Won't Fix`.

`Won't Fix` is therefore eligible even when Redmine has populated
`closed_on`. Other closed statuses are excluded. Branch evidence must come
from an explicit version/branch value in the ticket or journal; similar text,
the test name alone, or current source contents are not enough. Matching uses
full ticket journals fetched synchronously, and no missing branch or status
evidence is inferred.

For every eligible ticket, the tool extracts branch-specific occurrence
records containing the Redmine ID, detected version, testbed/setup, and pytest
test name. For a bug initially detected on the current branch, these values
come from its description and structured fields. For an older bug reproduced
on the current branch, they come from the same qualifying journal entry that
contains the current-branch evidence. A testbed or test case from an unrelated
branch occurrence must not be attached to the current branch. Missing values
remain blank.

Repeated occurrences are de-duplicated by Redmine ID, normalized branch,
testbed, and normalized pytest node ID. The test-case lists in this section
follow the case-folding rules below. Parameter variants may be folded, but
unrelated LogAnalyzer errors or Redmine tickets are not merged merely because
they affect the same test. File-level folding is allowed only when the complete
current-version execution inventory proves that every relevant non-skipped
case in the file belongs to that group; Redmine-only evidence is insufficient.

## Branches, hashes, and pull requests

The exact `--version` value is used to build:

```text
https://github.com/nvidia-sonic/sonic-buildimage/blob/<VERSION>/RC_STATUS.md
```

The private `RC_STATUS.md` supplies:

- image public hash from `Upstream base`;
- sonic-buildimage branch from `RC branch`;
- additional image PRs from the operation table.

The GitHub ref uses the exact `--version` without guessing or shortening. The
document's short release `Tag` (for example, `202608_RC.17`) must match the
deterministically extracted `<YYYYMM>_RC.<N>` portion of `--version`; a
mismatched tag records an error for the affected metadata and PR sections,
which remain blank. This also detects a force-updated ref that now contains a
newer RC document.

The release train is extracted from `--version`, and the sonic-mgmt branch is
selected from internal Gerrit as `develop-<YYYYMM>`. The local release
worktree head and the corresponding public `sonic-net/sonic-mgmt` GitHub
history are fetched and compared. The
public branch is resolved from internal synchronization evidence rather than
assumed from the image train; for example, both `develop-202605` and
`develop-202608` currently synchronize from public branch `202605`. Gerrit
imports can rewrite commit SHAs, so plain `merge-base` is not sufficient.
The tool walks local commits newest-first, resolves referenced public PRs,
and requires an exact stable patch-ID match against the public PR diff or
merge commit. The first validated match is the newest common content and its
GitHub commit is the sonic-mgmt public base hash. Commits after that base are
matched to the result of the synchronous Jenkins
`sonic_github_pr_report` execution.

The Git repository containing the current working directory is used, but the
caller's checked-out branch and files are never switched or modified. The tool
fetches the exact release ref into a dedicated temporary ref and creates an
isolated, detached temporary worktree for source analysis. It removes that
worktree after MIME construction. A non-Git directory, missing exact release
branch, fetch failure, or temporary-worktree failure disables source-dependent
analysis, leaves its derived fields blank, and records the error in the email.

The Jenkins report is not pre-generated. The mail workflow synchronously
starts the report operation with these parameters:

```text
ORG_NAME=
OVERWRITE_USERS=<newline-separated GitHub login list>
LITE=false
EMAIL_RECIPIENTS=<primary report recipient>
```

`OVERWRITE_USERS` accepts newline-separated GitHub login names, not display
names, email addresses, commas, or a JSON list. The mail workflow derives this
list from public PR references on commits after the resolved public base.
`ORG_NAME` is intentionally left at the Job's existing default. The Job still
scans its configured fork and repository lists; the author filter reduces
per-PR processing but does not eliminate unrelated repository queries.
`LITE` also remains at the Job default because its lightweight CSV writer
raises on records whose GitHub labels are absent.

The shared script and Jenkins Job are used without modification. The Job
retains its existing email behavior and writes the fixed file:

```text
fit74:/tmp/csv/Github_sonic_open_pull_requests.csv
```

The workflow pins the Jenkins queue item to its exact build number, waits for
that build to finish successfully, and then immediately reads the fixed file
over SSH from `fit74`. It never reads `lastSuccessfulBuild`. The current Job
deletes `/tmp/csv` at the beginning of every build, so a later queued build can
race this read. Such a missing or replaced result is reported as a generation
error in a degraded email; it cannot be eliminated without changing the Job
configuration or archiving an artifact.

Because the shared CSV writer does not quote commas reliably, the consumer
extracts only exact
`https://github.com/sonic-net/sonic-mgmt/pull/<number>` URLs with a URL
pattern. It fetches authoritative title, state, author, base branch, and
commit metadata from GitHub rather than trusting shifted CSV columns.

If the exact release branch does not exist or no valid common commit can be
established, the tool leaves branch-derived values blank, includes the error
in the generated message, sends that degraded message, and exits nonzero. It
never chooses a nearby branch or guesses a hash.

Only PRs proven to be public `github.com` URLs are included. Gerrit links,
private `nvidia-sonic` PRs, and other internal review URLs are rejected from
the PR sections even though the mail itself is internal.

## OpenCode contract

OpenCode may:

- classify and fold failures using non-empty engineer `analysis`;
- fold parameter variants of the same pytest case;
- fold a Python file when every executed case in that file failed;
- combine failures that share an existing human conclusion;
- combine and summarize distinct engineer analyses within a validated group;
- identify the concrete skip condition or case-level skip source from the
Excel skip reason and the checked-out sonic-mgmt source;
- fold the validated testbed and test-case occurrence lists for eligible
  LogAnalyzer tickets;
- summarize live eligible Redmine conclusions and derive a concise
Redmine-free `Comments` value;
- summarize the validated groups and generate the email wording.

OpenCode must not:

- diagnose a failure from raw exception text;
- invent a root cause, issue, pull request, owner, or status;
- treat a closed Redmine issue as current, except for an explicitly eligible
  `Won't Fix` LogAnalyzer bug in the internally detected error section;
- change pass/fail/skipped counts;
- move a failure to another image version;
- omit a failure or place it in more than one final group.

Code validates the model output before rendering. Invalid output is retried
and is never used. If retries fail, deterministic data remains unsummarized,
the affected AI-derived fields stay blank, and the generated message includes
the validation error.

## Case folding

Before OpenCode is called, code supplies stable record identifiers and
execution counts. The final grouping must satisfy these rules:

1. Repeated lifecycle rows for the same
  `session_id + mars_key_id + test name` are one failure record.
2. Parameter variants such as `test_x[a]` and `test_x[b]` may be displayed as
  `test_x[*]`; the email retains failed and executed variant counts.
3. A `.py` file may be represented by one file-level group only when every
  non-skipped, uniquely executed case from that file failed.
4. A file with at least one passing case cannot be folded to file level.
5. Distinct comments in one group are concatenated after exact duplicate and
  whitespace normalization.
6. `skip` and `xfail` records are never folded together when the original
  JUnit type is available.
7. Skip rows from the same test file are folded into one display group. Every
   distinct Excel reason and validated source predicate remains in that
   group's comments; rows from different test files are never merged.
8. Internally detected LogAnalyzer groups retain their Redmine/error identity.
  Their test-case lists use rules 1-4, but file-level folding additionally
  requires a complete current-version execution inventory; journal text alone
  cannot prove full-file coverage.

## Email table contracts

### Hardware reports

Rows are derived from Excel and use these columns:

```text
HardwareSku | Topology | ReportId | Internal Comments
```

- `HardwareSku` and `Topology` come from unique Excel pairs.
- `ReportId` is intentionally blank.
- `Internal Comments` summarizes failures, skipped coverage, or review notes
affecting that hardware/topology pair.

### Failure Analysis

```text
Test | Testbed | Comments | Internal Comments
```

- `Comments` is concise and safe for a future Microsoft-facing email. It
contains no Redmine or internal-only references but may retain public
GitHub PRs.
- `Internal Comments` contains the complete review evidence, concatenated
engineer analyses, active Redmine references, owner, status, and relevant
public PRs.

### The following tests were skipped

```text
Testbeds | Test Names | Comments | Internal Comments
```

- `Comments` is the concise, external-safe skip explanation.
- `Internal Comments` identifies the exact conditional mark, platform/topology
condition, unsupported feature, issue, fixture, or case that caused the
skip.
- The checked-out sonic-mgmt source and Excel `message` are evidence inputs.
- If the condition cannot be resolved without guessing, `Comments` may retain
the reported Excel reason, but the uncertain causal detail in `Internal Comments` is blank.

### Err msgs detected internally

```text
Testbeds | Test Cases | Error | Internal Comments
```

- `Testbeds` and `Test Cases` contain only occurrences with explicit
  current-branch evidence from the ticket description, structured fields, or
  the same qualifying journal.
- `Test Cases` uses the validated case-folding rules; parameter counts are
  retained whenever parameter variants are collapsed.
- `Error` is a concise rendering of the LogAnalyzer signature or normalized
  title and does not combine unrelated Redmine tickets.
- `Internal Comments` contains the Redmine link, current status, branch
  evidence source, and any non-inferred review conclusion.

## Skip mapping file

After the folded `The following tests were skipped` table is built, the
command atomically creates or replaces this file:

```text
<excel-directory>/skips.json
```

It is a UTF-8 JSON object that maps each canonical Redmine ticket URL extracted
from a folded row's `Internal Comments` to that row's Excel-derived skip
reason from `Comments`:

```json
{
  "https://redmine.mellanox.com/issues/5154543": "Warm reboot not supported on SPC6",
  "https://redmine.mellanox.com/issues/5042499": "Fast reboot not supported on SPC6",
  "https://redmine.mellanox.com/issues/4988548": "https://github.com/sonic-net/sonic-buildimage/issues/27006",
  "https://redmine.mellanox.com/issues/5090075": "Internal issue, WIP",
  "https://redmine.mellanox.com/issues/5150914": "Internal test issue, WIP",
  "https://redmine.mellanox.com/issues/5171381": "Internal issue, WIP",
  "https://redmine.mellanox.com/issues/5065405": "Internal issue, WIP",
  "https://redmine.mellanox.com/issues/5172208": "Internal test issue, WIP"
}
```

Only tickets referenced by the selected `--version` rows are written. If one
ticket maps to multiple distinct reasons, the reasons are de-duplicated,
whitespace-normalized, sorted deterministically, and joined with `"; "`. A row
without a Redmine ticket produces no JSON entry. If a ticket is available but
no skip reason can be extracted from the selected Excel rows, its value is the
exact fixed string:

```text
skipped by internal ticket，WIP。
```

The file contains the current invocation only; existing content is not merged,
so stale mappings cannot survive. When the selected version has no skipped
rows, the file contains `{}`. It is not attached to the email. Failure to write
it is reported in the email and makes the final exit status nonzero, but does
not prevent the email attempt.

## Known coverage issues

Known coverage issues are generated automatically. For every skipped test,
the tool:

1. Reads the Excel skip `message` and normalized pytest node ID.
2. Extracts public GitHub issue URLs directly from the Excel `message`.
3. Locates the matching conditional mark, decorator, fixture, or runtime skip
  in the test-time sonic-mgmt revision when available.
4. Confirms which HWSKU, topology, ASIC, platform, version, or feature
  condition caused the skip.
5. Fetches each extracted public issue's title and current state from GitHub.
6. Groups tests that share the same issue and effective skip condition.

Only conditions that affected the supplied Excel results are included. A
public issue is still reported when the checked-out code actively skips the
test, even if GitHub marks the issue closed; `Internal Comments` flags that
the closed issue is still gating coverage.

If the Excel `message` contains no public GitHub issue URL, the condition and
affected tests are retained and the issue field is blank. A source-code issue
reference that is absent from the Excel message is not promoted into this
section. OpenCode may summarize discovered conditions but may not invent an
issue URL.

If the exact source revision, JUnit type, CLI options, selected DUT/ASIC,
runtime facts, dependency outcome, or issue status at execution time is
missing, the reported Excel reason is retained but the causal condition is
left blank. Current issue status or current branch contents must not rewrite
the historical reason.

## Generated message

The command generates one internal-review MIME message:

- plain-text alternative;
- HTML report body;
- `<input-stem>_with_internal_comments.xlsx` attachment.

The attachment adds an `internal comments` column to the original result
sheet. The source workbook is never overwritten.

If any generation stage fails, the command still builds the best deterministic
message possible. Unavailable values and sections remain blank rather than
being guessed.

The HTML body contains:

- a prominent `Generation Errors` section when any stage failed, listing the
  failed stage, a sanitized concise error, and its impact;
- image, branch, and commit metadata;
- coverage and pass-rate summary;
- the Excel-derived HWSKU/topology table with blank report IDs;
- folded failure analysis with `Comments` and `Internal Comments`;
- folded skipped-test summary with resolved skip conditions;
- known coverage issues;
- live open or `Won't Fix` SONIC - Design LogAnalyzer matches;
- public-only image and sonic-mgmt pull requests.

## Error containment

Data-source, Git, Jenkins, Redmine, OpenCode, workbook enrichment,
`skips.json`, attachment, and normal HTML-rendering failures do not prevent a
send attempt. Each failure is isolated to its affected fields or section and
added to both the plain-text and HTML `Generation Errors` sections. Normal
HTML-rendering failure uses a minimal plain-text diagnostic MIME message.

Email-visible errors must not contain credentials, API tokens, SMTP
authentication data, raw environment dumps, or full stack traces. Detailed
diagnostics remain in the deployment log. Missing data is never replaced with
an AI guess.

An email cannot be sent when there is no valid recipient, SMTP cannot accept
the message, or the process cannot construct even the minimal diagnostic MIME
message. These are delivery blockers rather than report-generation blockers.

## Process output

Fully successful invocations are silent:

- no standard output;
- no standard error;
- exit status `0`.

Success means every required stage completed and the SMTP relay accepted the
message. Exit status `0` does not guarantee final mailbox delivery.

When a degraded email is accepted by SMTP, the command still writes one
concise summary to standard error and exits with the nonzero status for the
most severe generation error. Detailed diagnostics go to the deployment log.

## Exit status

```text
0  Success
2  Invalid command-line arguments or recipients
3  Invalid Excel or Git input
4  Regression-report API, external source, synchronous job, or matching failure
5  OpenCode execution or output-validation failure
6  SMTP connection, minimal MIME construction, or send failure
```

Exit statuses `3` through `5` may therefore mean that a degraded email was
successfully sent. Exit status `6` means delivery or MIME construction itself
failed; no successful email delivery may be assumed.

## Environment

These environment variables configure deployment without changing the CLI
contract:

```text
REGRESSION_MAIL_SMTP_HOST    Default: mailgw.nvidia.com
REGRESSION_MAIL_SMTP_PORT    Default: 25
REGRESSION_MAIL_SENDER       Default: nbu-system-sw-sonic-ver@exchange.nvidia.com
REGRESSION_MAIL_MODEL        Default: nvidia-hub/azure/openai/gpt-5.6-sol
REGRESSION_MAIL_API_BASE_URL Default: https://regression-report.mec01-asgard.nvidia.com
REGRESSION_MAIL_JENKINS_URL  Default: https://nbuprod.blsm.nvidia.com/nbu-sws-sonic/job/sonic_github_pr_report
REGRESSION_MAIL_JENKINS_CSV_PATH Default: /tmp/csv/Github_sonic_open_pull_requests.csv
REGRESSION_MAIL_JENKINS_SSH_HOST Default: fit74
REGRESSION_MAIL_JENKINS_SSH_USER Default: current VDI user
REGRESSION_MAIL_JENKINS_AUTHORS Optional comma/newline-separated GitHub login override
REGRESSION_MAIL_JENKINS_USER Optional Jenkins build user; pair with API token
REGRESSION_MAIL_JENKINS_API_TOKEN Optional secret; required when anonymous build is denied
REGRESSION_MAIL_OPENCODE     Default: opencode
REGRESSION_MAIL_OPENCODE_TIMEOUT Default: 900 seconds
REGRESSION_MAIL_OPENCODE_PARALLELISM Default: 10 concurrent evidence chunks
REGRESSION_MAIL_HTTP_TIMEOUT Default: 60 seconds
REGRESSION_MAIL_JENKINS_TIMEOUT Default: 1800 seconds
REGRESSION_MAIL_REPO_ROOT    Default: detected sonic-mgmt repository root
REGRESSION_MAIL_LOG_PATH     Default: unset; deployment may provide a protected diagnostic log
GITHUB_TOKEN                 Override only; default: authenticated VDI gh credential
```

SMTP uses STARTTLS. Credentials and API keys must not be committed to the
repository. OpenCode uses the credentials already configured on the
execution host.

OpenCode evidence remains capped at 50 semantic groups per invocation to
avoid model truncation. Independent chunks run concurrently and are merged
back in source order. Reduce `REGRESSION_MAIL_OPENCODE_PARALLELISM` if the
execution VDI or model provider enforces a lower concurrency limit.

## Jenkins API token

Anonymous users can read this Jenkins instance but cannot start
`sonic_github_pr_report`. Create a token while logged in to Jenkins:

1. Open the user menu in the upper-right corner.
2. Select `Configure` or `Security`.
3. Under `API Token`, select `Add new Token`.
4. Name it `regression-mail`, generate it, and copy it once.
5. Confirm that the user has `Item/Read` and `Item/Build` permission for
   `sonic_github_pr_report`.

Store the token only in a protected VDI environment file:

```bash
umask 077
vi <remote-sonic-mgmt-root>/.regression-mail.env
chmod 600 <remote-sonic-mgmt-root>/.regression-mail.env
```

Example contents:

```bash
REGRESSION_MAIL_JENKINS_USER=svc-sonic-regmail
REGRESSION_MAIL_JENKINS_API_TOKEN=<generated-token>
REGRESSION_MAIL_JENKINS_AUTHORS=zypgithub
REGRESSION_MAIL_JENKINS_SSH_USER=svc-sonic-regmail
REGRESSION_MAIL_LOG_PATH=/tmp/regression-mail.log
```

Do not put this file, the token, or a command containing the token in source
control or Jenkins console output.

The designated VDI may use `csh`/`tcsh` as its login shell. The environment
file uses Bash syntax and must not be sourced directly from a `%` prompt.
Start `bash` first:

```bash
bash
cd <remote-sonic-mgmt-root>
set -a
source .regression-mail.env
set +a
```

The checked-in remote wrapper already invokes Bash and does not have this
interactive-shell issue.

## Calling the VDI from another Jenkins job

OpenCode, its MCP authentication, GitHub SSO, and the internal source checkout
live on the designated VDI. A calling Jenkins job should not recreate those
credentials. It should invoke the checked-in `run_on_vdi.sh` wrapper over SSH.

Provision these Jenkins credentials:

- an SSH private-key credential for a dedicated account such as
  `svc-sonic-regmail`, authorized for the execution VDI;
- a Secret File containing pinned `known_hosts` entries for the VDI and any
  proxy jump host.

Bind those credentials to environment variables, then use this build step:

```bash
export REGRESSION_MAIL_VDI_TARGET="svc-sonic-regmail@execution-vdi"
export REGRESSION_MAIL_VDI_KEY_FILE="$VDI_SSH_KEY"
export REGRESSION_MAIL_VDI_KNOWN_HOSTS="$VDI_KNOWN_HOSTS"
export REGRESSION_MAIL_VDI_PROXY_JUMP="svc-sonic-regmail@jump-host"  # omit when direct
export REGRESSION_MAIL_REMOTE_ROOT="/persistent/path/sonic-mgmt"
export REGRESSION_MAIL_REMOTE_REVISION="$GIT_COMMIT"

bash ngts/scripts/regression_mail/run_on_vdi.sh \
  --excel "$COLLECTED_RESULTS_XLSX" \
  --version "$SONIC_VERSION" \
  --to "$REGRESSION_REPORT_RECIPIENT"
```

The remote checkout must be deployed at the same immutable commit specified by
`REGRESSION_MAIL_REMOTE_REVISION`. The wrapper verifies that revision, loads
the protected remote environment file, runs the command non-interactively,
and propagates its exit status to the calling Jenkins build. The Excel path
must be on storage visible from the VDI, such as `/auto`; a workspace-local
file must be copied to shared storage before this step.

The service account, rather than an individual engineer, owns the VDI
checkout, SSH key, OpenCode/MCP sessions, GitHub credential, and Jenkins API
token. `REGRESSION_MAIL_JENKINS_AUTHORS=zypgithub` remains only a PR author
filter and is not an authentication identity.

## Synchronous automation workflow

Production uses one synchronous workflow on the designated VDI:

1. Validate the Excel input and exact `--version`.
2. Query regression-report APIs and `RC_STATUS.md`.
3. Resolve and pin the internal and public sonic-mgmt histories.
4. Query Redmine live, including the dedicated SONIC - Design LogAnalyzer
   search and full journal evaluation described above.
5. Run the shared `sonic_github_pr_report` job synchronously with the
   newline-separated author list, immediately read its fixed CSV from `fit74`
   over SSH, and validate public sonic-mgmt PRs.
6. Invoke OpenCode for validated grouping and prose.
7. Atomically write `skips.json` beside the input workbook, render the
   attachment and MIME message, include accumulated generation errors, and
   send through SMTP.

There are no scheduled Redmine scans, periodic PR cache jobs, or
pre-generated source snapshots. Every source needed by an email is acquired
and validated in the same workflow invocation. The read-only OpenCode project
agent and prompts are versioned in this repository. Redmine access remains
read-only and uses the authenticated MCP configured on the VDI.

## Examples

Validated RC70 demo input:

```bash
python3 -m ngts.scripts.regression_mail \
  --excel "/auto/sw_regression/system/SONIC/release_results/202605_RC.70-2e2faf00ae_Internal/collected_results_26-08-11_Tue_10:37:35_202605_RC.70-2e2faf00ae_Internal.xlsx" \
  --version "202605_RC.70-2e2faf00ae_Internal" \
  --to "reviewer@nvidia.com"
```

On full success, the command produces no console output. A degraded email
produces a concise standard-error summary and a nonzero exit status.