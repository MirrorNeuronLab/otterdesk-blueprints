# Validation

The converted blueprint is checked using the actual published ARM64 Linux RGX 0.0.1 binary in its Debian Bookworm Docker worker environment.

- Architecture suite: 63 tests passed, including 45 graph-query subchecks. This covers all graph families, lazy caches and publication failure behavior, exact provenance, invalid citations, bounded knowledge, source acquisition, and the three SDK specialist handlers with durable replay.
- Final packaged-image smoke check: all three `/app` worker handlers produced a review draft (7 queries, one finding, zero model calls); replay returned the same durable outputs. Image: `mirror-neuron/achitecture-advisor:local`.
- Shared graph-analysis skill: 16 tests passed independently.
- Native macOS policy/contract suite: 29 passed, 34 Linux-binary tests skipped. Those skipped tests passed in Docker.
- Python compilation and `git diff --check` passed.

The complete catalog gate remains blocked by existing `mirrorneuron.dev` UI extension schema identifiers in other blueprints, while the current SDK expects `mirrorneuron.io`: the manifest suite has three failures and the full suite stops on two collection errors. This blueprint compiles successfully with the current schema.

Default checks use deterministic hash embeddings or scripted models, with no live model or repository-network requests. The GitHub acquisition test exercises real Git checkout and revision capture while substituting a local fixture for HTTPS transport. Live model quality and a full core/Redis orchestration run are not covered by these checks.
