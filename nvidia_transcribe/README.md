# NVIDIA Transcribe

Read an audio folder and produce complete Markdown transcripts using
`nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-NVFP4`. The conservative default
requires one NVIDIA Blackwell GPU with 96 GiB memory and a Linux runtime. This
NVFP4 checkpoint cannot run on a 48 GB L40S or substitute another precision.

The coworker accepts WAV, FLAC, MP3, OGG and M4A, including nested folders and
uppercase extensions. It transcribes files one at a time in sorted relative-path
order, finishing every chunk of one recording before starting the next. It
uses the shared `mirrorneuron-folder-files-skill` for recursive discovery and
keeps audio format and size policy in this blueprint. It
freezes a source snapshot, normalizes audio to 16 kHz mono, transcribes every
ordered 300-second chunk through the SDK model journal and saves one
`transcripts/<relative filename>.md` per input. The authoritative
`transcription_result.json` records hashes, durations, model revision, coverage
times, empty-response flags, measured word/speaker timing and durable transcript
references. A failed or truncated response fails the batch; saved responses are
not dispatched twice.

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
silently truncated. Chunk headings mark input coverage and may divide words.
Word timings come separately from NeMo's CTC alignment, never interpolation.
Speaker labels are anonymous, scoped to one chunk, and can be incorrect.
Review important text against the recording.

## Interactive transcript

After **all recordings finish** and their Markdown/index are delivered, the
blueprint publishes an optional `web/index.html` report and `web_ui.json` handle.
It uses the runtime's `mirrorneuron-web-report-skill` shell, Geist fonts, Actions
menu, shared controls and details panel. No blueprint web server is started.

Choose a recording, then press **Play**. The round table has one anonymous human
avatar per detected speaker in the current section. Speaking avatars and the
current words highlight together; the transcript follows playback. Overlapping
speakers can highlight together. Select a word or use the timeline to seek;
change speed or turn **Follow transcript** off to read at your own pace.
Playback advances through sections automatically and never starts on page load.

Select an avatar to enter a name. Names survive reload in the same browser and
are isolated by run, source and section. They do not change the saved model text.
Separate chunks do not establish persistent identity: the table and names reset
at each section boundary. Unknown speakers do not create invented avatars.

Keep the entire `web/` directory together when moving the report; `web/audio/`
contains captured 16 kHz mono WAV sections. Each recording has a separate HTML
page to bound page size. Audio and names stay local; the report has no remote
assets, telemetry or runtime controls. Open the runtime Web UI or the report in
a browser for playback. The desktop's current cached report iframe does not
serve audio assets; this blueprint does not modify that desktop restriction.

Missing, failed, incomplete or malformed alignment withholds the interactive
report for the batch. Markdown transcripts still complete; the run records a
diagnostic. Optional rendering/audio-delivery errors likewise cannot invalidate
the authoritative transcripts. No partial or live report is advertised.

Workers use Python 3.12 and a lightweight Docker image. The independent model
image uses Python 3.13, CUDA 13.2, vLLM 0.32.0 and pinned NeMo Speech. The
replay model recipe reuses the published `homerquan/nvidia-transcribe` base by
SHA-256, with Linux amd64 and arm64 variants. It adds the bundled NeMo timestamp
middleware and trusted timestamp request options. The new model identity is
`nvidia-nemotron-3.5-transcribe-nvfp4:0.2.0`; the previous image does not enable
this middleware. Build the `0.2.0` image on the model node before using this
source revision (it has not been published by this code change):

```bash
docker build -f nvidia_transcribe/payloads/model/replay.Dockerfile \
  -t homerquan/nvidia-transcribe:0.2.0 nvidia_transcribe/payloads/model
```

Before a catalog release, publish both supported image architectures and replace
the development tag in `execution.json` with the verified image digest. Full
rebuild sources remain in `payloads/model/Dockerfile`. The SDK starts the model
only for the first transcription, downloads
the pinned NVFP4 checkpoint and caches weights and kernels under its managed
volume. Job preparation, folder discovery and audio normalization do not download
model weights. Model and worker operations reuse the Job allocation.
First-use kernel compilation is limited to four build jobs with one NVCC thread
per job so compilation and the loaded model fit Spark's shared CPU/GPU memory.

```bash
synapsy verify ./nvidia_transcribe --workspace /path/to/mirror-neuron-set --compile --python /path/to/runtime/python
python -m pytest nvidia_transcribe/tests -q
cd nvidia_transcribe/tests && npm ci && npx playwright install chromium
PYTHON=/path/to/runtime/python npm test
```

Created using Synapse's concrete-plan `synapsy create --plan` path. Offline checks
cover compiled dispatch, full chunk coverage, Markdown, immutable snapshots,
replay, optional report failure isolation, actual browser audio playback, speaker
naming, seek/speed/follow controls, empty states and responsive layouts.
Browser fixtures contain synthetic tones and timing data, not live inference.
CUDA startup, NVFP4 kernels, CTC timing and transcript quality
require separate live qualification; no live transcript is bundled.
