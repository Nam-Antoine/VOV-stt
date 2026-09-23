# LICENSE NOTICE — do not remove

This file records third-party licence constraints that bind this project. It is referenced
by PLAN.md §0.3. Removing or weakening it is not a maintenance decision.

## ASR model — `hynt/Zipformer-30M-RNNT-6000h`

The model is licensed **CC BY-NC-ND 4.0**.

- **Non-commercial (NC).** This is a paid client project. Pilot and evaluation use is fine;
  **production billing requires written permission from the author (`hynt` on Hugging Face)**.
  That permission has not been obtained as of 22 Sep 2026.
- **No derivatives (ND).** No fine-tuning. No re-export of the model or a modified model
  under our name. We ship the author's ONNX files unmodified, downloaded at deploy time by
  `scripts/download_models.py`; they are not vendored into this repository.
- **Attribution (BY).** Any published output or documentation must credit
  `hynt/Zipformer-30M-RNNT-6000h`.

The sibling model `hynt/sherpa-onnx-zipformer-150m-vi-2026-09-09` is a separate work with a
separate licence. Check it before using it for anything beyond the pilot A/B.

## Punctuation model — `welcomyou/vibert-capu-onnx` (readable layer only)

ONNX export of `dragonSwing/vibert-capu`, licensed **CC BY-SA 4.0**.

- **Commercial use is allowed**, with attribution (BY) to `dragonSwing/vibert-capu` and
  `welcomyou/vibert-capu-onnx`.
- **Share-alike (SA)** binds adaptations *of the model*. We ship the files unmodified,
  downloaded by `scripts/download_models.py`, and do not fine-tune them.
- It produces the **readable layer** only (`utterances.text_readable`, the
  `readable.txt` / `readable.docx` exports): punctuation and capitals for reading. The
  verbatim corpus (`text_asr`, `text_verified` and every corpus export) never passes
  through it (CLAUDE.md rule 1).

## Data residency

Audio stays in Vietnam. Self-hosting is what answers the Decree 13/2023 cross-border
personal-data question that the ElevenLabs route raised.

If the optional second engine (ElevenLabs Scribe) is ever enabled, that question **reopens**
and needs a client decision before any audio leaves the host. It is behind the `ENABLE_SCRIBE`
feature flag, **off by default**.

## Speakers

Vox-pop voices are identifiable private individuals. Do not build speaker-identification
features that try to name them. Speaker labels are per-episode cluster IDs plus a free-text
label that the verifier types.

## Other components

| Component | Licence |
|---|---|
| `sherpa-onnx` runtime | Apache-2.0 |
| Silero VAD (`silero_vad.onnx`) | MIT |
| `pyannote/segmentation-3.0` ONNX export (csukuangfj) | MIT (weights: see pyannote model card) |
| Speaker-embedding ONNX (3D-Speaker / WeSpeaker, csukuangfj) | Apache-2.0 — verify per file |
| This application code | Client-owned; see the engagement contract |
