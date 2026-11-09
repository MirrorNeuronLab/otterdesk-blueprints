# NVIDIA Transcribe user manual

Choose an authorized local folder containing WAV, FLAC, MP3, OGG or M4A files.
Nested folders are supported. Or select the bundled Bdb001.interaction.wav sample,
about 50 minutes of audio. Start a run with normal Job controls; Chat never starts
work by itself. The coworker writes one `transcripts/<relative filename>.md` per
recording and an authoritative `transcription_result.json` inventory.
The default output folder is `~/Downloads/nvidia-transcribe`. Each delivered
batch has its own `run_<timestamp>/` subfolder.

It processes files one at a time in sorted relative-path order, including nested
WAV and MP3 files. It finishes each recording before transcribing the next,
using ordered 300-second chunks. Heading times
mark input coverage. Separate measured word timings drive the finished web
report. Transcripts preserve spoken wording and
may contain errors, especially at chunk boundaries or with overlapping speakers.
An empty model response is marked explicitly; no speech is invented to fill it.

Limits: 100 audio files, 2 GiB total input, 256 MiB and two hours per recording.
Requires a Linux NVIDIA Blackwell node; default memory floor is 96 GiB, based on
NVIDIA's documented NVFP4 profile. A generic 48 GB NVIDIA GPU is insufficient for
this exact checkpoint. The first transcription installs/reuses the pinned model
through the SDK; later runs use its cache. Audio is sent only to that managed
node. The model image does not contain the sample recording.

Inspect `get_run_status` and `get_run_results` for observed completion. A failed
file rejects completion; the batch index is published only after every recording
has a complete saved transcript. Pausing/stopping uses normal Job controls.

After the entire batch finishes, open its Web UI or `web/index.html` in a browser.
Press Play to hear the captured audio, follow highlighted words and see who is
speaking around the table. Click a word to seek; use Speed or Follow transcript
to change playback or scrolling. The section selector moves through long audio.
Choose another recording from the top selector. Playback never starts by itself.

Click an avatar to set a name. Names are remembered in this browser for this
run, recording and section; they do not edit the original transcript. Speaker
identification is anonymous and restarts in each section. The model does not
establish persistent identities across sections or recordings.

If timing cannot be verified, only the Markdown is published. A failed optional
report does not invalidate a saved transcript. Keep the complete `web/` folder,
including audio, when moving the report. For sound, open the runtime web report
or a browser; the desktop cached report viewer currently blocks audio assets.
