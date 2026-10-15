# Product Readiness Retrieval Notes

Financial advisor runs should be evaluated on evidence grounding, privacy boundaries, and review-only behavior.

Useful retrieval targets include:

- bank statement extraction evidence and transaction total checks
- household cash-flow review and fee/debt risk language
- tax document routing, source-field extraction, and manager-review blockers
- portfolio market-data freshness, concentration, and deterministic risk math
- human approval boundaries for filing, trading, bill payment, money movement, and external sharing

A production-ready run writes stable artifacts, keeps logs redacted, records source references, and makes missing evidence visible. Browser or market-data failures may continue with warnings when the primary local evidence path is intact; they must not become silent fallback advice.
