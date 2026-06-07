# Safety Video Analyser

Batch blueprint for validating smart node allocation and BlobRef video sharing.

- `video_understanding_agent` requests `otterdesk-video-watch:default` and high-end NVIDIA placement.
- `report_generator` uses the default Gemma 4 Docker Model Runner LLM and suggests `mirror_neuron@192.168.4.173`.
- Local videos are read from `~/Downloads/videos` and staged under `safety_video_analyser/mn_local_inputs/videos`.
