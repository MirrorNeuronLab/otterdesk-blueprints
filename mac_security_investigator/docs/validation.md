# Validation record — October 7, 2026

## Logs-only update (0.2.0)

Native collection now queries unified logs only. Startup directory enumeration,
plist parsing and installation-marker inspection have been removed. Host/user
log history is isolated from the earlier startup-snapshot ledger. Reports mark
startup changes and attributed executions as not evaluable from diagnostic
metadata; unavailable or partial log coverage remains explicit.

- 38 focused co-worker, manifest and source/binary dependency checks passed,
  including all four SDK message handlers and tests that forbid OS-file reads
  during acquisition. The test runtime uses the installed source environment
  plus pytest; it does not write to the real user home directory.
- Blueprint JSON, Python syntax and Git whitespace checks passed.
- An opt-in read-only native collection succeeded on this Mac, retaining 2,000
  diagnostic records. Byte/record caps and private-value/retention limits were
  reported as partial coverage. No message text or OS-file contents were retained.
- The broader suite remains affected by existing procurement dependency imports,
  stale sample paths and test-environment dependencies; it is not a passing gate.

Updating the existing stable Job through the conditional bundle API could not
complete: its revision changed and the co-worker was subsequently archived.
The archived Job and its history were left intact. The installed Job still has
the earlier bundle; no live workflow run of 0.2.0 has been verified. These results
do not certify detection accuracy or runtime/cluster privacy.

Synthetic/local validation for version 0.1.0:

- 21 co-worker tests passed, including all four native SDK message handlers,
  persistent Job isolation, idempotent report replay, reversed/duplicate imports,
  occurrence attribution, counterevidence, denied coverage, bounded search,
  untrusted content and context graph scope/cutoff checks.
- 103 selected catalog/dependency/RAG checks passed. Thirteen checks for existing
  CCTV/Architecture entries were deselected because their current dependency
  pins differ from the older assertions. The new entry's source and binary
  dependency-staging contracts passed; this does not publish its new skill.
- 66 temporal/graph skill tests passed. The full non-E2E skills gate passed
  410 tests, with 2 skipped, 3 deselected and 12 subtests passed.
- Shared skill genericity audit and generated Agent Skills drift check passed.
  The temporal skill built an offline wheel successfully.
- The inert synthetic result preview was inspected at 1,000px and 480px, after
  wide-to-narrow resize, with no page overflow. No evidence links or scripts ran.
- Blueprint JSON parsing, Python compilation and Git whitespace checks passed.

The complete blueprint suite could not pass in the current shared checkout. Its
first attempt stopped at an existing procurement import of the removed
`mn_document_reading_skill`. An attempt excluding that collection error found
additional existing blueprint/import/version failures (including installed RAG
packages older than sibling source). The one new-entry failure identified there,
the test assuming every RAG extension is enabled, was fixed by testing the
effective enabled profile and separately asserting private-evidence RAG is off.
The final selected catalog gate above passed after that correction.

No live private Mac scan, native Membrane server execution, remote model,
cluster placement/locality certification, signing, installer or GAR publishing
was performed. Context transport tests verify the caller contract; the engine's
own tests own actual recursive SQL execution. Live macOS source capability and
empirical detection quality remain release gates in the acceptance matrix.

## Local placement and automatic setup update

The follow-up change declares `runtime.placement.must_run_local` and a Darwin
requirement, and reduces the public input/default configuration to output folder
only. Capture now discovers standard launchd roots, identifies a local history
epoch and queries a bounded unified-log scope. Logs retain redacted metadata,
not message text or inferred startup-execution identities.

Validation uses injected placement reports and native log-reader fixtures,
never private user logs. The SDK non-E2E gate passed 1,727 tests; focused CLI
placement/model checks passed 49 tests and API launch/placement checks passed
54 tests. The complete CLI/API gates still have unrelated existing Cosmos3
catalog failures. The co-worker/manifest gate passes and its four handler
entrypoints execute against sealed synthetic scans. Native log streaming tests
cover timeout, byte caps, permission failures, process validation and child
cleanup. The new log skill builds an offline wheel; genericity and generated
portable-catalog checks pass.

The broader skills gate cannot collect the existing web-browser tests in the
available environment because `curl_cffi` is missing. The broader blueprint gate
has the existing procurement dependency collection failure; the Membrane
catalog gate has an existing CCTV SDK-version assertion failure. Source changes
have not been deployed to the installed runtime and no live private scan or
native context-engine run was performed.
