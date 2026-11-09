# NVIDIA Transcribe coworker specification

Transcribe every supported recording in an authorized staged audio folder to one
Markdown file, preserving relative names and appending `.md`. The required exact
model is `nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4`, revision
`66c6adc4020179567074d0399cda2a4eeb2bb347`. No alternate model or precision is used.

Shared `folder_files_skill` discovery includes nested folders and
case-insensitive audio extensions, with this blueprint's existing limits. Files
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
The blueprint requests speaker-attributed word timestamps from the same pinned
model using its bundled NeMo CTC middleware. It validates finite, bounded timing,
word coverage, diarizer mappings and speaker activity before displaying them.
It never estimates timing from chunk length or assumes that a repeated speaker
tag in another chunk identifies the same person. Missing or failed alignment
withholds the optional replay while preserving completed Markdown.

Only after the complete batch's authoritative publication succeeds may the
blueprint publish its optional static report and handle. It uses the shared
runtime web report template unchanged, with domain-owned table, transcript and
playback controls. The generated page adds only same-origin media to the
template's restrictive CSP. The runtime remains a static presentation transport;
no service, new shared skill, desktop change or runtime change is required.

The current section's detected speaker count determines the anonymous avatar
count. Word timing controls the lyric-like highlight and internal transcript
scroll; diarization controls speaker emphasis and supports overlapping voices.
Playback, pause, seek, speed, section/recording choice and follow controls are
keyboard accessible, do not autoplay and honor reduced motion. Selecting an
avatar opens the shared name editor; display names are browser-local and scoped
to run/source/section. They never rewrite authoritative evidence. Unknown voices
and empty transcripts remain explicit. Long names retain full tooltips.

Captured normalized WAV sections and recording pages ship under `web/`. The
entry page and handle are published last. Failed optional UI rendering or
delivery must not reject the saved transcript batch. Playback is supported in
the runtime web report/browser; the desktop cached iframe's media restrictions
are outside this blueprint's ownership. The 0.2.0 model image requires a build
with the timestamp-enabled entrypoint before live use and a digest pin before
catalog release. No container is built or published by ordinary tests.

Persistent speaker identities across sections, live streaming and accuracy
guarantees remain outside this co-worker's contract.
