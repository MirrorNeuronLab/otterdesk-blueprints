# Safety Video Analyser

Batch blueprint for reviewing local workplace video footage with smart node allocation and BlobRef video sharing.

- `video_understanding_agent` requests `otterdesk-video-watch:default` and hard NVIDIA CUDA placement.
- `write_safety_report` writes review-only JSON and Markdown reports using the local run-store artifact contract.
- Local videos are read from `safety_video_analyser/examples/sample_inputs` by default and staged by BlobRef before analysis.
- The bundled `worksite_safety_walkthrough.mp4` is a tiny generated demo clip. Replace it with approved real footage for meaningful safety review.

## Outputs

Runs declare the standard run-store artifacts plus domain artifacts:

- `video_analysis.json`
- `safety_video_report.json`
- `safety_video_report.md`
- `final_artifact.json`

The report should stay evidence-bound and human-review only; it must not certify safety or trigger operational action by itself.
