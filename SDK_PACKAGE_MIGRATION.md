# SDK package migration

All ten catalog blueprints now use `dependencies.json.packages` for SDK workflow
capabilities. `skills` contains domain skills, and `agents` contains reusable
agent packages. Each package and skill entry uses `type: "pip"`, `source: "gar"`,
a full distribution name, and an exact release version.

The capability names below have the distribution prefix `mn-python-sdk-`.
Common contracts and other required component dependencies are resolved
transitively; an installed optional provider is never enabled implicitly.

| Blueprint | Declared SDK capabilities | Retained domain skills |
|---|---|---:|
| `cctv_operator` | common, web-ui, job-response, mcp, rag[milvus] | 1 |
| `purchasing_manager` | common, rag[milvus], job-response, mcp | 2 |
| `drug_discovery_research_assistant` | models, job-response, mcp, rag[milvus], web-ui | 0 |
| `legal_assistant` | common, rag[milvus], job-response, mcp | 1 |
| `research_assistant` | common, rag[milvus], job-response, mcp | 3 |
| `gtm_assistant` | collaboration, rag[milvus], job-response, mcp | 2 |
| `software_architecture_advisor` | common, job-response, rag[milvus], mcp | 1 |
| `microduck_controller` | web-ui | 0 |
| `litigation_analyst` | job-response | 3 |
| `achitecture_advisor` | job-response | 1 |

## Installation behavior

- Local SDK installation selects sibling projects under `mn-python-sdk/packages`.
- Local skill mode (`MN_USE_LOCAL_SKILLS=1`, set by local setup) selects shared
  projects under `mn-skills` or blueprint-owned projects under `payloads/skills`.
  Resolution uses the distribution name in `pyproject.toml`, ignoring the
  blueprint's release version. Ambiguous source names fail explicitly.
- Binary mode retains GAR pins and does not automatically substitute bundled
  skill source. The architecture graph skill therefore has a GAR declaration
  without `path` or `format`, while its source project remains available for
  development.
- SDK preparation removes release pins for localized distributions, preserves
  extras, and installs source projects together in one pip transaction. Both
  HostLocal and DockerWorker paths are covered, including generated Dockerfiles
  and root build contexts with nested Dockerfiles.
- Payload imports now use the new packages, SDK integrations, and agent-owned
  actor/tool-session helpers. Removed payload bootstraps no longer maintain a
  second package list. Email delivery remains a skill.

## Release prerequisites

| Distribution group | Target version |
|---|---|
| SDK capability packages | `0.1.0` |
| Shared `mirrorneuron-*-skill` packages | `1.3.23` |
| `mn-prototype-*-agent` packages | `1.3.10` |
| Blueprint-owned `mn-software-architecture-graph-skill` | `1.3.22` |

Deploy an SDK release containing the new dependency schema and publish the
above package versions before GAR-based deployment. The previous shared skill
and agent release tags predate the moved APIs. No packages were published by
this change. Binary installation was tested with locally built wheels.

## Verification

- OtterDesk catalog regression: **276 passed, 35 skipped, 3 deselected**.
- Catalog-wide declarations, import resolution, and source/binary preparation:
  **40 passed**, including generated worker contexts for CCTV.
- SDK and component tests: **1,255 passed**, one optional end-to-end test excluded.
- Package/component infrastructure: **98% combined line/branch coverage**;
  package validation, component dependency resolution, registry, and native
  host preparation each reached **100%**.
- Fresh editable and wheel installations: SDK-only, RAG-only, and all seven
  providers passed; package dependency consistency passed in both environments.
- CLI submission regressions: **111 passed**. API regressions: **231 passed**
  across the sandbox run and a separate localhost-socket run.

The catalog run excludes tests targeting the separate `mn-blueprints`
repository (VC, Financial Advisor, and ROS AMR). That repository still needs
its own migration; it was not edited here. Existing Linux RGX/live-service
skips remain. GPU, ROS, external model/service runs, and GAR publication were
not performed.
