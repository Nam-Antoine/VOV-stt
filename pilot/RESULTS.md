# Pilot results (PLAN §4) — NOT RUN YET

**Status: T2 has not started.** This file is a placeholder so the gate is visible in the
repo. `pilot/run_pilot.py` overwrites it when the sweep runs.

## Gate (PLAN §4.2) — all four must pass

| Check | Passes if | Result |
|---|---|---|
| **Verbatim** | Fillers *à, ừ, thì, là, ờ* appear where the docx has them; repetitions and false starts survive. Filler recall ≥ 0.85. | — |
| **Diarization** | MC, guest and ≥ 2 distinct vox-pop voices on separate cluster IDs. | — |
| **Timestamps** | Clicking a word plays that word within ~200 ms. | — |
| **Names/terms** | *Thanh Huyền, Di Li, quản chồng, giữ lửa* come through with hotwords loaded (compare with/without). | — |

Plain WER is reported alongside, with **no normalisation** beyond lowercasing and
stripping punctuation from the reference.

## What T2 needs before it can run

- [ ] The audio for the `TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx` episode, located on
      vovlive.vn / vtcnews.vn.
- [ ] `pilot/clip_2min.wav` — a 2-minute cut containing **both** studio dialogue and a
      vox-pop segment.
- [ ] `pilot/reference.txt` — that span transcribed verbatim from the docx,
      `SPEAKER<TAB>text` per line.
- [ ] `make models` (already possible today).
- [ ] `pip install jiwer` for WER (`pip install -e "backend[pilot]"`).

Then: `make pilot`.

## Known engine risk (PLAN §2)

The model card says the training labels were "refined using Whisper", and Whisper-style
labels tend to drop fillers. **Filler recall is unknown until this pilot runs.** If
verbatim fails on every setting in the §4.3 sweep, stop and escalate — do not proceed to
the web app on this engine.

## Decision

- [ ] 30M vs 150M:
- [ ] Chosen knobs written to the `settings` table:
- [ ] **Owner sign-off on verbatim:**
