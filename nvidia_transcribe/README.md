# NVIDIA Transcribe

Read an audio folder and produce complete Markdown transcripts using
`nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4`. The conservative default
requires one NVIDIA Blackwell GPU with 96 GiB memory and a Linux runtime. This
NVFP4 checkpoint cannot run on a 48 GB L40S or substitute another precision.

The coworker accepts WAV, FLAC, MP3, OGG and M4A, including nested folders and
uppercase extensions. It transcribes files one at a time in sorted relative-path
order, finishing every chunk of one recording before starting the next. It
freezes a source snapshot, normalizes audio to 16 kHz mono, transcribes every
ordered 300-second chunk through the SDK model journal and saves one
`transcripts/<relative filename>.md` per input. The authoritative
`transcription_result.json` records hashes, durations, model revision, coverage
times, empty-response flags and durable transcript references. A failed or
truncated response fails the batch; saved responses are not dispatched twice.

The default **Output folder** in setup is `~/Downloads/nvidia-transcribe`.
MirrorNeuron delivers each batch to a `run_<timestamp>/` subfolder there.

```bash
mn blueprint run ./nvidia_transcribe --set inputs.payload.input_folder=/absolute/path/audio
```

Select the bundled sample to use `examples/sample_inputs/Bdb001.interaction.wav`,
copied in full from the user-provided recording. It is about 50 minutes long,
16 kHz mono PCM, and is neither synthetic audio nor an observed transcript.
Its SHA-256 and duration are in `examples/sample_source.json`. The recording
is excluded from the model build context; no source recording is published with
the container image. The sample's inclusion does not grant public redistribution.

Inputs are bounded to 100 audio files, 2 GiB total, 256 MiB and two hours per file.
Non-PCM formats use the worker's FFmpeg with a 180-second deadline. No file is
silently truncated. Chunk headings mark input times and may divide words; they
are not word-level alignments or speaker identification. Review important text.

Workers use Python 3.12 and a lightweight Docker image. The independent model
image uses Python 3.13, CUDA 13.2, vLLM 0.32.0 and pinned NeMo Speech. The
model recipe pins the published `homerquan/nvidia-transcribe` image by SHA-256,
with Linux amd64 and arm64 variants. Rebuild sources are in `payloads/model/`;
ordinary use pulls the image automatically. The SDK starts it only for the first transcription, downloads
the pinned NVFP4 checkpoint and caches weights and kernels under its managed
volume. Job preparation, folder discovery and audio normalization do not download
model weights. Model and worker operations reuse the Job allocation.
First-use kernel compilation is limited to four build jobs with one NVCC thread
per job so compilation and the loaded model fit Spark's shared CPU/GPU memory.

```bash
synapsy verify ./nvidia_transcribe --workspace /path/to/mirror-neuron-set --compile --python /path/to/runtime/python
python -m pytest nvidia_transcribe/tests -q
```

Created using Synapse's concrete-plan `synapsy create --plan` path. Offline checks
cover compiled dispatch, full chunk coverage, Markdown, immutable snapshots,
replay and explicit failure. CUDA startup, NVFP4 kernels and transcript quality
require separate live qualification; no live transcript is bundled.
