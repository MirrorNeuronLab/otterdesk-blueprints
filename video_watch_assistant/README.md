# Video Watch Assistant

`Blueprint ID:` `video_watch_assistant`
`Category:` `Security`

A video-watch co-worker for monitoring an approved local or mapped video stream. Give it the stream source, visual targets, alert policy, and optional input folder assets; it detects configured objects or activities and writes reviewable observations, counts, positions, confidence, and alert status artifacts to the output folder.

## What It Does

This folder is a self-contained MirrorNeuron blueprint. It defines the runtime
manifest, default configuration, payload code, local documentation, and any
fixtures needed to review or run the workflow from this checkout.

## Quick Start

Run from the catalog:

```bash
mn run video_watch_assistant
```

Run directly from this folder:

```bash
mn run --folder .
```

Inspect recent run state:

```bash
mn blueprint monitor --follow
```

## Inputs And Configuration

- `manifest.json`: graph shape, entrypoints, runtime metadata, runners, services, and environment access.
- `config/default.json`: default launch configuration, visual targets, alert policy, mapped RTSP demo source, and mock/sample input settings.
- `config/overwrite.json`: optional local overrides layered on defaults.
- `payloads/`: worker scripts, policies, fixtures, prompts, and support files used by this blueprint.
- `examples/sample_inputs/watch_policy.json`: concrete target and alert-policy sample shown during onboarding and validation.

Key init fields are `video_source.uri`, `inputs.payload.visual_targets`, `inputs.payload.alert_policy`, input folder, and output folder. The default optional websocket fan-out is deliberately disabled and marked as a mock integration until `MN_BLUEPRINT_EVENTS_WS_URL` is configured and the output skill is enabled through launch overrides.

## Outputs

Most runs write artifacts under `~/.mn/runs/<run_id>/`. Common files include
`events.jsonl`, `result.json`, `final_artifact.json`, worker logs, and generated
reports when the blueprint produces them.

For video-watch runs, inspect `events.jsonl`, `final_artifact.json`, and `web_ui.json` for target detections, confidence, cooldown decisions, human notices, and optional alert routing status.

## Safety Checklist

- Review `manifest.json` and `payloads/` before running with real data.
- Check `pass_env`, provider credentials, Slack/email/web adapters, and any shell or OpenShell runners.
- Start with mock, dry-run, or quick-test configuration before live external integrations.
- Keep local customer overrides out of committed defaults.

## Local Documentation

- [SPEC](SPEC.md)
- [TERM](TERM.md)
- [License](LICENSE.md)

- [Manifest](manifest.json)
- [Default config](config/default.json)

## Validation

Run repository-level tests from `otterdesk-blueprints` after changing catalog metadata,
manifest structure, payload behavior, or shared fixtures:

```bash
cd ..
.venv/bin/python -m pytest -q
```
