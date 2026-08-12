Review the attached regression-mail evidence JSON and return exactly the
`required_output` JSON shape.

The top-level object must use these exact snake_case keys:
`schema_version`, `failure_groups`, `skip_groups`,
`internal_error_groups`, and `executive_summary`. Emit
`"schema_version": 1` as a JSON number. Do not rename or omit these keys.

The evidence may be one chunk of a larger report. Process every supplied
`source_group_id`, but do not refer to groups that are not attached. When
`include_internal_errors` is false, do not query LogAnalyzer bugs and return
an empty `internal_error_groups` list. When it is true, perform that review
once for this invocation.

Failure review:

1. Keep every supplied failure `source_group_id` exactly once in output
   `member_ids`.
2. Engineer analysis is the only base diagnosis. If it is empty, do not
   diagnose from another field.
3. Query SONiC Verification and SONiC Design only when needed to find explicit,
   current evidence for the supplied version, test, testbed, platform, or
   HWSKU.
4. `internal_comments` may retain eligible Redmine links and existing human
   conclusions. `comments` must be concise and contain no Redmine or
   internal-only reference.

Skip review:

1. Keep every supplied skipped `source_group_id` exactly once in output
   `member_ids`.
2. Inspect the supplied source root for matching conditional marks,
   decorators, fixtures, or explicit runtime skip sites.
3. Do not claim a historical runtime predicate unless the supplied evidence
   proves its source revision and relevant facts.
4. When unresolved, retain the Excel message in `comments` and leave uncertain
   causal detail blank in `internal_comments`.

Internally detected errors:

1. Query SONIC Design bugs authored by `LogAnalyzer User`, tracker `Bug SW`.
2. Include only open-category or exact `Won't Fix` statuses.
3. Include a ticket only when its description/field says it was detected on
   the supplied image branch, or one journal explicitly records reproduction
   on that branch.
4. Testbed and test-case values for an older ticket must come from that same
   branch-qualifying journal. Missing values remain blank.
5. Keep separate Redmine/error identities in separate groups. These groups
   have an empty `member_ids` list.

Do not emit any fact that cannot be tied to the attached evidence, inspected
source, or a read-only Redmine result.
