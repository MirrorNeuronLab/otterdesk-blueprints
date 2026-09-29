# Domain boundary violations

**Section:** 03 · Natural boundaries versus current boundaries  
**Specification ID:** `AR-03-05`  
**Customer question:** Where does one domain reach into another domain’s rules or internal representation?

## What to include

- State the intended domain boundaries and the evidence or stakeholder input used to define them.
- Identify cross-domain access to internal models, tables, business rules, or lifecycle decisions.
- Explain the invariant or ownership expectation that the access undermines.
- Propose a contract, ownership clarification, or deliberate documented exception.

## Why this matters

Domain violations can make a business-rule change affect areas that should not need to understand it. Naming the violated rule makes the analysis more actionable than flagging every cross-domain dependency.

## Evidence to use

Use domain documentation, schema and write paths, interface definitions, imports, and representative changes. Distinguish an established rule from the reviewer’s proposed model.

## Expected report output

A domain-boundary matrix and finding list with source domain, target domain, accessed internals, affected invariant, and proposed remedy.

## Completion and quality checks

Cross-domain communication is not automatically a violation. The report must identify the inappropriate dependency or mark the boundary itself as disputed.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
