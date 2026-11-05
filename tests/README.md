# Blueprint tests

OtterDesk catalog, product composition, dependency ranges, package transport,
activity and current-consumer checks live here. `mn-system-tests` keeps runtime
contracts and the `mn-blueprints` demo catalog.

Use the shared development environment with the SDK, API, CLI, Membrane benchmark
package and `mn-system-tests` test utilities installed:

```sh
uv pip install --python ../mirror-neuron-set/mn-system-tests/.venv/bin/python -r tests/requirements.txt
../mirror-neuron-set/mn-system-tests/.venv/bin/python -m pytest tests -q
```

`fixtures/catalog_transport_v2.json` preserves the reviewed authored baselines
imported from the runtime suite. Unreviewed product changes still fail their
owning catalog gate; moving the tests does not approve or refresh those changes.
The existing product-specific tests remain alongside these catalog checks.

Native Rust integrations are opt-in and create isolated storage and ports:

```sh
RUN_OTTERDESK_NATIVE_CONTEXT_TESTS=1 ../mirror-neuron-set/mn-system-tests/.venv/bin/python -m pytest tests/test_native_context_integration.py tests/test_litigation_original_context_integration.py -q
```

The remote task benchmark requires an already configured SSH workspace and both
explicit capability gates. It does not install or reset a runtime:

```sh
RUN_OTTERDESK_TASK_BENCHMARK=1 MN_ENABLE_TWO_BOX=1 MN_ENABLE_GPU_TESTS=1 ../mirror-neuron-set/mn-system-tests/.venv/bin/python -m pytest tests/test_blueprint_task_benchmark.py -q
```

Set `MN_CLUSTER_REMOTE_SSH`, `MN_CLUSTER_REMOTE_MN_SET_FOLDER` and, optionally,
`OTTERDESK_TEST_RESULTS_DIR` for the remote command. Frozen benchmark sources
must match the reviewed fixture before any SSH or staging takes place.

The Litigation/public-source quality diagnostic is also owned here:

```sh
../mirror-neuron-set/mn-system-tests/.venv/bin/python tests/diagnostics/source_context_quality.py --help
```

It requires explicit `--live`, workspace/catalog paths, a fresh output directory,
an endpoint, model and installed digest. Runtime-only fault controls remain in
`mn_system_tests.benchmarks.runtime_quality`; no model run is part of the default gate.
