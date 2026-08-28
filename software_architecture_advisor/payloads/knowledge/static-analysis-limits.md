# Static-analysis evidence limits

The architecture evidence is built without executing code. It can provide
useful evidence about repository metadata, syntax symbols, declared imports,
package boundaries, module complexity, dependency fan-in/fan-out, strongly
connected cycles, state/trust patterns, direct test links, deployment
declarations, and pre-staged history facts.

It cannot prove runtime dispatch, dynamically computed imports, deployed
topology, database authority, test coverage, data flow, exploitability,
performance, or production risk. History is unavailable unless a normalized
history JSON file is staged. Treat absent evidence as unknown rather than
evidence that behavior or risk is absent.
