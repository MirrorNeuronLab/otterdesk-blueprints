# Software architecture advice report
## Content specification library

**23 section folders · 150 aspect specifications · Markdown**

This library turns the 23-section report outline from the conversation into
individual content specifications. It describes a decision-ready architecture
report: what the system does, how it works, where its risks and constraints lie,
what changes would affect, and how to turn recommendations into verifiable work.

These are proposed report-content requirements, not a completed assessment of a
codebase, benchmark results, or independently validated customer research. No
repository analysis, runtime testing, or production changes are included.

## Start here

Open the [complete index](INDEX.md) to browse every section and aspect. Read the
[shared report conventions](REPORT_CONVENTIONS.md) for evidence, confidence,
coverage, prioritization, and implementation boundaries. Each section also has
its own `README.md` with a linked contents table and related sections.

The [machine-readable manifest](manifest.json) lists the section order, purpose,
all specification IDs, paths, customer questions, word counts, and SHA-256 hashes
for the aspect files. It can be used to drive a report-generation workflow or
check which aspects have been covered.

## File structure

```text
software-architecture-advice-report-specs/
├── README.md
├── INDEX.md
├── REPORT_CONVENTIONS.md
├── manifest.json
├── executive-architecture-brief/
│   ├── README.md
│   ├── what_the_system_does_spec.md
│   ├── overall_architecture_shape_spec.md
│   ├── major_strengths_and_weaknesses_spec.md
│   ├── top_architectural_risks_spec.md
│   └── immediate_vs_later_priorities_spec.md
├── inferred-system-architecture/
│   ├── README.md
│   ├── major_subsystems_and_responsibilities_spec.md
│   └── ...
├── ...
└── implementation-ready-work-packages/
    ├── README.md
    ├── task_goal_spec.md
    ├── relevant_files_and_components_spec.md
    ├── architectural_constraints_spec.md
    ├── non_goals_spec.md
    ├── migration_steps_spec.md
    ├── required_tests_spec.md
    ├── acceptance_criteria_spec.md
    └── coding_agent_handoff_spec.md
```

The ellipses above abbreviate the tree; the [complete index](INDEX.md) lists every
actual file. The archive contains 177 files: 150 aspect specifications, 23 section
READMEs, and these four top-level files.

## What each specification contains

| Field | Purpose |
| --- | --- |
| Customer question | The decision or understanding this aspect serves. |
| What to include | Concrete required content, scope, and distinctions. |
| Why this matters | The customer value and the reason the content belongs in the report. |
| Evidence to use | Appropriate inputs and important evidence limitations. |
| Expected report output | The narrative, table, matrix, diagram, register, or task to produce. |
| Completion and quality checks | Conditions that make the output useful and prevent overclaiming. |

Each file has a stable catalog ID, such as `AR-01-01`, and links to its section
contents, the complete index, and shared reporting conventions. Focused
cross-references connect overlapping diagnostic and decision topics.

## Using the library

Treat a specification as a content contract for a report writer, analyst, or
report-generation step. Supply the review scope and actual evidence separately.
For each aspect, record applicability and analysis coverage. Produce the required
content or explicitly identify what evidence is missing and what should be
verified. Do not interpret the presence of a spec as a requirement to find a
problem.

Use the same canonical component, evidence, finding, and recommendation IDs across
sections. The report should connect observations to decisions rather than repeat
the same issue in several forms. Write the executive brief after completing the
supporting analysis. Work packages remain proposed until separately authorized;
the report does not grant permission to edit, deploy, or modify production data.

## Section inventory

| # | Section | Aspect files |
| --- | --- | ---: |
| 01 | [Executive architecture brief](executive-architecture-brief/README.md) | 5 |
| 02 | [Inferred system architecture](inferred-system-architecture/README.md) | 6 |
| 03 | [Natural boundaries versus current boundaries](natural-boundaries-vs-current-boundaries/README.md) | 5 |
| 04 | [Hidden coupling](hidden-coupling/README.md) | 6 |
| 05 | [Change blast-radius analysis](change-blast-radius-analysis/README.md) | 8 |
| 06 | [Architecture hotspots](architecture-hotspots/README.md) | 7 |
| 07 | [Architecture debt and smells](architecture-debt-and-smells/README.md) | 9 |
| 08 | [Data and state ownership](data-and-state-ownership/README.md) | 9 |
| 09 | [Critical workflow analysis](critical-workflow-analysis/README.md) | 7 |
| 10 | [Reliability and failure architecture](reliability-and-failure-architecture/README.md) | 6 |
| 11 | [Scalability ceilings](scalability-ceilings/README.md) | 6 |
| 12 | [Performance and latency architecture](performance-and-latency-architecture/README.md) | 6 |
| 13 | [Security and trust boundaries](security-and-trust-boundaries/README.md) | 6 |
| 14 | [Architecture evolution](architecture-evolution/README.md) | 6 |
| 15 | [Team and architecture alignment](team-and-architecture-alignment/README.md) | 5 |
| 16 | [Decision and what-if analysis](decision-and-what-if-analysis/README.md) | 6 |
| 17 | [Alternative target architectures](alternative-target-architectures/README.md) | 4 |
| 18 | [Concrete prioritized recommendations](prioritized-recommendations/README.md) | 7 |
| 19 | [Sequenced migration and refactoring roadmap](sequenced-migration-roadmap/README.md) | 8 |
| 20 | [Business impact](business-impact/README.md) | 8 |
| 21 | [Evidence and confidence](evidence-and-confidence/README.md) | 8 |
| 22 | [Unknowns and verification tasks](unknowns-and-verification-tasks/README.md) | 4 |
| 23 | [Implementation-ready work packages](implementation-ready-work-packages/README.md) | 8 |

**Version:** 1.0 · **Created:** September 16, 2026
