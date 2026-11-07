# NVIDIA Transcribe coworker specification

Transcribe every supported recording in an authorized staged audio folder to one
Markdown file, preserving relative names and appending `.md`. The required exact
model is `nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4`, revision
`66c6adc4020179567074d0399cda2a4eeb2bb347`. No alternate model or precision is used.

Discovery includes nested folders and case-insensitive audio extensions. Files
are transcribed sequentially in sorted relative-path order; every chunk and the
saved transcript for one recording precede inference on the next recording.

One stock domain-operation step owns folder policy and reporting. Reusable audio
preparation and model request construction belong to `nvidia_transcribe_skill`.
The SDK owns immutable file snapshots, per-chunk effect journals, model admission,
placement, installation and result delivery. Domain hooks never invoke Docker or
implement workflow routing, retries, ACKs or logical completion.

Limits are 100 files, 2 GiB total, 256 MiB and two hours per file. Every decoded
sample is included exactly once in ordered chunks of up to 300 seconds. Native
16 kHz mono PCM WAV is read directly; other formats use bounded FFmpeg decoding.
Model requests fit the SDK binary payload bounds. Output text is at most 4 MiB
per recording. Stop/length/refusal validation rejects incomplete responses.

Completion requires all transcript Markdown files and `transcription_result.json`
to be durably published. The index binds file hashes, durations, exact chunk
coverage, the pinned model and transcript references. Empty responses are
qualified explicitly. A failed file prevents successful batch completion; partial
private work remains available for recovery. Replays use captured source and
committed responses, including when original files change after capture.

Requirements: Linux, NVIDIA Blackwell, conservative 96 GiB GPU memory floor,
8 CPU cores, 16 GiB CPU RAM and 100 GiB disk. Serving startup checks actual
Blackwell capability. Python 3.12 workers and the isolated Python 3.13 upstream
model environment are separate. Model weights are installed lazily on first
required request; images contain serving code only. The admitted Job allocation
covers all worker/model work. Inputs and transcripts are confidential.
First-use FlashInfer builds use at most four parallel compilation jobs and one
NVCC thread per job to bound host memory pressure on unified-memory nodes.

The bundled sample is the user's full Bdb001.interaction.wav recording with
hash/duration provenance. It is excluded from public model images. Acceptance
requires complete coverage and correct output receipts in offline fixtures, and
a separate representative live transcript on the intended Blackwell node.
Word alignment, persistent speaker identities, live streaming and accuracy
guarantees are outside this coworker's contract.
