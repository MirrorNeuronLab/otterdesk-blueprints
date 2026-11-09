# Transcription worker

While a batch runs, OtterDesk shows audio duration processed and average audio
seconds per second in Chat's run monitor and workflow detail. Each completed
audio chunk updates the measurement; an unfinished chunk is not counted. The
average includes model preparation and request overhead. Recovery uses original
call timings. Deploy the matching SDK with `ProcessingProgress` to the worker
and API, then reprepare the co-worker to enable these readings.

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

The default **Output folder** in setup is `~/Downloads/transcription-worker`.
MirrorNeuron delivers each batch to a `run_<timestamp>/` subfolder there.

```bash
mn blueprint run ./transcription_worker --set inputs.payload.input_folder=/absolute/path/audio
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
change speed or turn **Follow** off to read at your own pace.
Playback advances through sections automatically and never starts on page load.

The full-size report keeps the speaker table on the left and the scrolling
transcript on the right. In the workspace panel, the table stays above the
scrolling transcript.

Select an avatar to enter a name. Names survive reload in the same browser and
are isolated by run, source and section. They do not change the saved model text.
Separate chunks do not establish persistent identity: the table and names reset
at each section boundary. Unknown speakers do not create invented avatars.

Keep the entire `web/` directory together when moving the report; `web/audio/`
contains captured 16 kHz mono WAV sections. Each recording has a separate HTML
page to bound page size. Audio and names stay local; the report has no remote
assets, telemetry or runtime controls. Play it from **Full report** in OtterDesk,
the runtime Web UI, or by opening `web/index.html` in a browser.

Missing, failed, incomplete or malformed alignment withholds the interactive
report for the batch. Markdown transcripts still complete; the run records a
diagnostic. Optional rendering/audio-delivery errors likewise cannot invalidate
the authoritative transcripts. No partial or live report is advertised.

Workers use Python 3.12 and a lightweight Docker image. The independent model
image uses CUDA 13.2, vLLM 0.32.0 and pinned NeMo Speech.
`execution.json` pins the published timestamp-enabled image by digest for Linux
amd64 and arm64. The `0.2.0` image tag also serves Jobs prepared with the older
recipe. New Jobs use the `0.2.1` model recipe identity so the runtime can keep
both Docker configurations separate.

`payloads/model/replay.Dockerfile` adds the timestamp-enabled entrypoint to the
pinned base. Publish both architectures and verify the registry digest before
updating the model recipe. Full rebuild sources remain in
`payloads/model/Dockerfile`. On the first transcription, the SDK starts the
model, downloads the pinned NVFP4 checkpoint and caches weights and kernels
under its managed volume. Job preparation, folder discovery and audio
normalization do not download model weights. Model and worker operations reuse
the Job allocation.
First-use kernel compilation is limited to four build jobs with one NVCC thread
per job so compilation and the loaded model fit Spark's shared CPU/GPU memory.

```bash
synapsy verify ./transcription_worker --workspace /path/to/mirror-neuron-set --compile --python /path/to/runtime/python
python -m pytest transcription_worker/tests -q
cd transcription_worker/tests && npm ci && npx playwright install chromium
PYTHON=/path/to/runtime/python npm test
```

Created using Synapse's concrete-plan `synapsy create --plan` path. Offline checks
cover compiled dispatch, full chunk coverage, Markdown, immutable snapshots,
replay, optional report failure isolation, actual browser audio playback, speaker
naming, seek/speed/follow controls, empty states and responsive layouts.
Browser fixtures contain synthetic tones and timing data, not live inference.
CUDA startup, NVFP4 kernels, CTC timing and transcript quality
require separate live qualification; no live transcript is bundled.
