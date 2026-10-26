# Code verifier manual

Choose a local repository checkout or source/docs folder in the first setup
question. No source folder is selected by default. Start a run. The
co-worker reads documentation, creates rules.md, asks you to approve the rules
in this conversation, verifies approved rules one by one, and
writes report.md with pass/fail/unknown, exact evidence and confidence 0–1.
It does not execute or edit repository code or tests.

**Rule documents** defaults to **Project docs**. Generated benchmark/test reports
under benchmark-results, benchmark_results, test-results, test_results and
playwright-report are excluded from rule extraction and listed in
extraction-plan.json, rules.json and the report. They remain captured evidence.
Choose **All captured docs** to extract rules from those reports too.
The extraction packet budget defaults to 512 (`review.max_extraction_packets`,
1–2048); it never truncates the selected documents to fit.

Before verification, open **Review rules** in this conversation. Search the list
of short titles and select a rule to read its complete Markdown and source.
Choose **Edit Markdown**, preview your changes, then **Save rule** to update its
title or statement. Edits apply to this run and open a fresh review; saving never
approves the rules. Save or discard an open edit before approving.
**Approve all** confirms the entire saved list, including rules outside a search,
plus any displayed coverage gaps or investigation limits. **Reject** stops the
review. No reply or an unavailable review service never counts as approval.
The review expires after one hour by default. Approval applies only to the
current run, source capture and unchanged rules.

Add customized rules as Markdown files under this co-worker's Job knowledge
`rules/` folder, for example `rules/custom.md`. Each section has the form:

```markdown
## MY-RULE-ID — Short descriptive title

The software must enforce the stated condition.
```

Use one rule per heading, unique IDs (letters, digits, hyphens, underscores,
starting with a letter; 64 characters maximum), and no introductory prose.
Titles are optional and at most 120 characters. Use level-three or deeper
subheadings inside a rule. Exported rules.md retains titles and can be copied
into Knowledge to reuse changes from Chat.
`review.rules_mode=augment` adds these to extracted documentation rules. Retain
a generated GEN-... heading to override that rule. `review.rules_mode=replace`
verifies only your custom list; copy and edit the exported rules.md for this.
Save knowledge changes before starting a new run. An active run keeps its capture.

Pass requires implementation evidence; Fail requires a counterexample in source.
Unknown means evidence is insufficient or an investigation could not finish.
Documentation, test definitions and missing search hits are not execution proof.
Confidence is an uncalibrated AI assessment, capped at 0.85 for static judgments.
Review cited source, omissions and limitations before making decisions.

The normal output folder is ~/Downloads/code-verifier, with each run
in its runtime-delivered timestamp folder. Rules, full structured results,
captured source, hashes, syntax coverage and investigations accompany report.md.
Open the completed run's web report in this conversation to inspect rule results
and evidence in the workspace.
Remote URLs are not fetched; clone first. Convert PDF/Word/image docs to UTF-8
Markdown before selection. Never include unauthorized source or secrets.

Standard MCP tools inspect manual, capability, current state and results. Reading
or asking a question never starts work. Explicit run controls start, pause, resume
or stop the bound Job using runtime-issued execution IDs. Core owns operations
and cancellation. Inspect operation completion before assuming a run finished.
