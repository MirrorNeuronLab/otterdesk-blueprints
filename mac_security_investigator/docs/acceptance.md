# Temporal specification acceptance matrix

Version 0.2.0 is a logs-only pilot. Native collection reads unified-log metadata
only; it does not inspect startup/OS files. TB-01/TB-03 and execution attribution
are not evaluable from these logs. The startup-related entries below describe
synthetic temporal-analysis tests, not native collection capabilities.

Version 0.1.0 was the earlier startup-snapshot pilot. “Covered” below means a deterministic synthetic test
exercises the stated implemented scope; it does not certify platform capability
or empirical detection accuracy. The full supplied specification remains the
target. Missing capabilities are explicit, not inferred graph relationships.

| ID | Current status |
| --- | --- |
| T01 | Covered: same scoped slot, ordered target difference across runs. |
| T02 | Partial: execution enrichment spans runs; general delivery/installation progression awaits adapters and TB-02 policy. |
| T03 | Covered: scan replay and repeated archive imports do not inflate events/cases. |
| T04 | Covered: unchanged startup reobservations do not create another execution/change. |
| T05 | Covered: distinct source occurrence keys preserve identical event messages. |
| T06 | Covered: missing keys and disputed duplicates remain unresolved and uncounted. |
| T07 | Covered for imported keys: session-scoped execution identities; native execution adapter pending. |
| T08 | Covered: user scopes remain separate. |
| T09 | Partial: immutable captured configurations and digest differences; file-instance/version graph pending. |
| T10 | Pending: Mac filesystem identity/rename adapter. Existing graph skill file identity is reusable but not adopted as forensic identity. |
| T11 | Pending: reversible ambiguous rename/replacement decisions. |
| T12 | Covered: overlapping windows do not establish strict order. |
| T13 | Covered: scoped sequence order exposes clock conflict; no invented delay. |
| T14 | Covered: denied source is not absence. |
| T15 | Covered: complete comparable scoped absence supports observed return. |
| T16 | Partial: capabilities/parser/coverage retained and comparability gated; parser migration workflow pending. |
| T17 | Covered: late occurrence time stays separate from knowledge time. |
| T18 | Covered: independent installation corroboration explains the same case; old report retained. |
| T19 | Covered: untrusted note cannot clear the case. |
| T20 | Pending: identity merge/split ledger and invalidation. |
| T21 | Partial: retained immutable snapshots; no last-known state asserted as continuous validity. General historical joins pending. |
| T22 | Covered: temporally impossible aggregate paths rejected. |
| T23 | Covered within startup scope: persistence/change/recurrence never establishes malicious intent; expected update considered. |
| T24 | Covered: candidate/traversal caps report incomplete search. Resumable frontier pending. |
| T25 | Covered within startup scope: comparison retains all earlier anchors; no short report lookback. |
| T26 | Covered within startup scope: grouping requires scoped slot and connected change episode; generic target not a case anchor. |
| T27 | Pending: user-driven pruning and case availability revisions. No implicit evidence deletion. |
| T28 | Covered for atomic commits and run artifact replay; abrupt process-kill fault injection pending. |
| T29 | Partial: acquisition windows and non-atomic status; bounded redacted unified-log metadata and blocked OS-file reads are tested with fixtures; macOS live validation pending. |
| T30 | Covered: knowledge cutoffs and exact saved report JSON/text. |
| T31 | Covered: state-only analysis with execution unknown, not invented. |
| T32 | Covered within retained startup history: old anchors retained; total history cap disclosed. |
| T33 | Covered: only the fixed read-only Apple log utility; no shell, inspected source execution, remediation, source links or remote context destination; preview escapes content with restrictive CSP. |
| T34 | Covered for final supported startup/case semantics under reordered and duplicate batches; arrival revision history may differ. |

Required next release work: native historical-source capability validation;
TB-02/TB-05; identity merge/split and time correction; source pruning; bounded
affected-region indexes and resumable search; expanded timeline interaction;
standalone runtime locality/placement verification; benign/controlled pilot corpus
and independently reported precision, identity, provenance and false-case metrics.

This matrix does not claim the full security MVP's definition of done is met.
