# Mac security investigator

This co-worker reviews local Mac unified-log evidence across user-initiated
runs and preserves source receipts, coverage and saved reports. It runs on the
submitting Mac. Version 0.2.0 is a logs-only pilot; it does not inspect OS files
or certify that a Mac is safe.

## Setup

**Output folder is the only co-worker setting.** It defaults to
`~/Downloads/mac-security-investigator`. Log scope, host/user history scope and
collection limits are automatic. There is no scan mode, input archive, host ID,
startup-folder list or knowledge-cutoff field.

```bash
mn blueprint run ./mac_security_investigator
```

To choose the report destination:

```bash
mn blueprint run ./mac_security_investigator --set outputs.folder_path=~/Downloads/security-reviews
```

Use the same hired Job for successive scans. The co-worker queries the local
unified log datastore through Apple's `/usr/bin/log show`; no log folder needs
to be selected. It inspects the last 24 hours of default/info messages from
`launchd`, `syspolicyd`, `amfid` and `backgroundtaskmanagementagent`, capped at
4 MiB, 2,000 retained records and 20 seconds. It retains timestamps, logger
metadata and source-line digests, not message text or arguments. Logs are
diagnostic observations; this adapter does not turn them into attributed
startup executions or malicious findings.

The collector does not enumerate startup directories, open plists, inspect
installation markers, read executable contents or change OS files. It never
executes inspected targets or scripts, requests elevated access, changes startup
settings or performs remediation. Permission failures, parse errors,
retention/redaction and capacity limits appear in coverage. Unreadable evidence
never implies absence. Debug messages and archived log stores are outside this
collection. Runtime code, retained Job history and report files remain necessary
application-owned storage.

## Runtime and outputs

Use local development with the matching sibling SDK, agents and skills. The
`mirrorneuron-temporal-graph-skill` and `mirrorneuron-macos-logs-skill` must be
released before binary/GAR installation can resolve them. The local Core and
Membrane v2 service must already be prepared. The runtime's `MN_CONTEXT_ADDR`
must identify the local loopback endpoint; remote destinations are rejected.
Runtime service setup is separate from co-worker configuration.

Membrane navigates normalized assertions with exact source locators. Temporal
analysis uses deterministic witnesses. No inference model or reputation service
is used. Context service errors fail explicitly.

Authoritative outputs include `final_artifact.json`, `report.md`, `evidence.json`,
`analysis.json`, `context_graph.json` and sealed scan/revision artifacts.
`web/index.html` is an optional inert preview. The runtime supplies run paths
and copies reports to the selected output folder in a run-specific subfolder.
The persistent Job ledger is under `state/<epoch-digest>/history.sqlite3`.
The host/user log scope uses the Mac hostname and user identity without opening
installation markers. A changed host/user selects another ledger; this cannot
certify installation continuity across clones or restores. Logs-only history is
separate from the earlier startup-snapshot ledger, which is left intact. Two Jobs have separate histories. Older sealed runs keep their exact
reports when later evidence arrives.

Synthetic Northstar scans in `examples/sample_history/` are test fixtures only;
they are never the default run. The Python ledger API supports retrospective
revision queries and saved-report replay without a user-facing cutoff setting.
Logs-only runs do not evaluate startup target changes or observed return after
absence (TB-01/TB-03), execution attribution, actor identity or exact configuration
change time. Historical synthetic startup fixtures still test the temporal
analysis contract, but are not native capabilities. See [SPEC.md](SPEC.md) and
the [acceptance matrix](docs/acceptance.md).

## Locality requirement

`execution.json` declares `runtime.placement.must_run_local: true` and
`requirements.os: "darwin"`. API, OtterDesk and `mn` launches pin the Job owner,
specialists and generated control nodes to the submitting Mac. Hardware ranking
cannot choose Spark. Windows/Linux/unknown local platforms, explicit remote
assignments, and distributed placement fail before worker preparation.
This requires SDK `>=1.3.58.dev46,<2`; editing the blueprint does not upgrade an
installed runtime.
HostLocal Python runs through the Mac's native SDK service, including when Core
runs in Docker. Both the native investigator and Core's supervision proxy have
prepared environments. The native SDK service must support
`mn.native.host-python.v1`; refresh it after a source update.

Execution locality does not disable Core's shared-output replication. Private
evidence requires a standalone local runtime without cluster replication.
Dependency preparation is separate from investigation; this pilot does not
certify all runtime transports or chat routing as offline. The response service
receives capabilities only. Open the local report for private findings.

## Validation

```bash
python -m pytest tests/test_mac_security_investigator.py tests/test_manifest_contracts.py -q
```

From `mn-skills`:

```bash
python -m pytest macos_logs_skill/tests temporal_graph_skill/tests graph_analysis_skill/tests -q
python scripts/audit_shared_skill_genericity.py
python scripts/sync_agent_skills.py --check
```

Tests use synthetic evidence, temporary Job data, injected Mac/remote placement
reports, a native-reader fixture and fake context transport. Live private Mac
sources, runtime launch and native Membrane execution require separate validation.

Startup preparation was checked through both CLI doctor and the API: all four
native environments prepared successfully. A harmless Core HostLocal check
resolved all four handler modules on native macOS Python with exit code 0.
It did not submit an investigation or collect private Mac evidence. Runtime
doctor also reported a separate cluster coordination-store mismatch.
