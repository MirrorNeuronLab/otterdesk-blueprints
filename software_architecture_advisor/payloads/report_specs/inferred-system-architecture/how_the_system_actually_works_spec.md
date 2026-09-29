# How the system actually works

**Section:** 02 · Inferred system architecture  
**Specification ID:** `AR-02-06`  
**Customer question:** What operational story explains the implementation beyond its file layout?

## What to include

- Explain how the main subsystems collaborate from startup through representative work completion.
- Describe the control plane, data plane, configuration, and state lifecycle where those distinctions are relevant.
- Reconcile contradictions between documentation, source structure, and runtime observations.
- Call out surprising mechanisms, implicit assumptions, and unresolved parts of the reconstructed model.

## Why this matters

Customers need an explanatory model they can use in design reviews and onboarding. A synthesis of behavior is more useful than separate inventories that leave the reader to connect the dots.

## Evidence to use

Synthesize the subsystem, boundary, topology, dependency, and flow findings. Use direct implementation evidence to support departures from existing documentation.

## Expected report output

A concise walkthrough supported by a component view and a few representative execution narratives, with explicit observed/inferred/unknown labels.

## Completion and quality checks

Every major statement must reconcile with the underlying inventories. Do not treat intent as implementation or omit contradictions merely to make the story simpler.

Apply the [shared report conventions](../REPORT_CONVENTIONS.md), including
claim-level traceability, confidence, scope, and explicit handling of missing
evidence. This file specifies required content; it does not assert that an
analysis or test has already been performed.

---

[Section contents](README.md) · [Full index](../INDEX.md)
