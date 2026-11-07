# NVIDIA OCR coworker specification

Accept one authorized image or PDF and transcribe every page with
`nvidia/nemotron-ocr-v2` multilingual, revision
`0e83e83f17943524b90afa6c0fd82ac2bc1a40ca`. One stock native-computation step owns
durable model dispatch and recovery; the skill owns reusable OCR mechanics.

Completion requires committed `ocr_result.json`, `text.txt` and `document.md`.
JSON is authoritative and binds all pages to the source SHA-256 and model
revision, with model-ordered regions, normalized left/top/right/bottom boxes,
confidence and explicit empty-page warnings. No source content enters coordination
messages. Retries recover committed responses without repeating inference.

Requirements: Linux amd64, NVIDIA CUDA, one GPU with at least 49,152 MiB memory,
8 GiB CPU RAM, 4 CPU cores and 40 GiB disk. The Job allocation covers worker and
model use. Dependencies and model recipe are declared once in role documents.
No model download occurs on import, skill installation or Job preparation.
The image is prepared before execution; weights are installed lazily by the SDK
when the first valid native request starts the service.

Input is at most 32 MiB; up to 50 PDF pages, 25 million pixels per raster page.
PDFs render sequentially. Output is bounded to 8 MiB, 10,000 regions and 4 MiB
of text. Corrupt/unsupported inputs, resource failures, malformed responses,
mismatched hashes and publication errors fail explicitly. Empty text is reported,
not fabricated. Single-frame images only; OCR is not semantic table extraction.

Acceptance: sample text can be recovered in a separately qualified GPU run;
offline checks prove all pages are represented, hashes and output contracts
match, stock bindings compile and replay never repeats a saved model call.
Live GPU build and inference remain separate qualification gates.
