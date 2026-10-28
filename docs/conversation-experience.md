# Blueprint conversation profiles

All published packages expose optional app guidance at `payloads/prompts/conversation.json`, with schema `otterdesk.conversation_profile.v1` and the exact manifest ID. It is an OtterDesk asset, not a runtime extension or second catalog. It describes responsibility, evidence boundaries, limitations, allowed instruction kinds and eleven conversation stages. OtterDesk combines it with authoritative Job state, pending input, safe confirmed answers and selected run evidence.

| Blueprint | Saved instructions | Work and evidence boundary |
| --- | --- | --- |
| General Assistant | Communication and future task rules | Frozen task prompt; private Harness2 lessons remain private; public answer is a run-linked prepared source. |
| Research Assistant | Communication and future review rules | Post-tool review context only; public query planning and experimental approval stay unchanged. |
| Financial Advisor | Communication and future review rules | Reviewer context only; deterministic calculations and gates remain authoritative. |
| Procurement Manager | Communication and future review rules | Post-intake analysis context; no public-query leakage, ranking or transaction authority. |
| Architecture Advisor | Explanation preferences | Source snapshot and configured review files retain scope authority. |
| Code verifier | Explanation preferences | Exact Core rule-list approval and Job rule knowledge remain authoritative. |
| Litigation Analyst | Explanation preferences | Matter handling, legal review and source provenance retain authority. |
| VC Assistant | Explanation preferences | Scoring policy, public research permissions and company evidence remain unchanged. |
| Drug Discovery Research Assistant | Explanation preferences | Native scientific pipeline and computational scores remain unchanged. |
| CT reader | Explanation preferences | Native CT request unchanged; saved research report is a run-linked prepared source. |
| Mac security investigator | Explanation preferences | Capabilities-only Chat; private evidence remains in local ledger/Membrane. |
| CCTV Operator | Existing bounded Job memory | Camera notes, monitoring goals, secure source fields and timestamped observation evidence. |
| Microduck Controller | Existing bounded Job memory | Original control requests, live preflight and observed browser receipts. |
| ROS AMR Controller | Existing bounded Job memory | Existing zone aliases and restrictive rules; live motion and operation receipts. |

The optional app-managed `inputs.payload.supervisor_instructions` list has at most 50 unique records, 1,000 characters per text and 16,000 JSON UTF-8 bytes total. New runs capture supported work rules once. Later edits and forgetting do not change accepted runs or historical evidence. Ordinary corrections and dialogue never become long-term instructions implicitly.

Existing Membrane source intelligence and TextMemory consumers keep their current ownership and enablement. No chat transcript, credentials, private Harness2 memory or arbitrary input files are copied into runtime memory. Missing context is explicit; earlier reports remain historical. Bounded domain actions and memory keep their original runtime planner and validated receipts.

Validation uses the catalog inventory in `index.json`: `tests/test_conversation_profiles.py`, each domain's offline suites, and the full catalog tests. The desktop's `test:blueprint-conversations` command runs eight fake-inference contract cases per published blueprint. Those checks establish context delivery and isolation, not live language quality, clinical/scientific validity or robot safety qualification.
