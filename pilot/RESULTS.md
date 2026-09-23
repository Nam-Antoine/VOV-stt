# Pilot results (PLAN §4) — BLOCKED, NOT RUN

**Status: T2 cannot be scored as PLAN §4.2 specifies.** The blocker is the ground truth,
not the engine. Read this before treating any number below as a pass.

## Blocker — the supplied reference is not verbatim

`scripts/docx_to_reference.py` audits the docx it converts. On
`resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx` it reports:

```
grammatical words  :   286
punctuation marks  :   403
capitalised words  :   411
*** WARNING: this reference is not verbatim. ***
```

A spontaneous radio conversation carries far more hesitation markers than that. Combined
with the punctuation and casing counts, the docx has been edited into readable prose —
which is exactly what a hand-verified client transcript normally is.

Why that breaks the gate, in the plan's own terms:

* **Filler recall is `fillers_in_hyp / fillers_in_ref`.** With a near-zero denominator
  for *à / ừ / ờ / ừm*, the pooled figure is decided almost entirely by *thì* and *là* —
  ordinary words any ASR emits freely. It can read **> 0.85 while every real filler is
  being dropped**. The headline metric would be measuring nothing.
* **WER is inverted.** Fillers the engine *does* keep are scored as insertions against a
  reference that removed them, so the engine is penalised for the wanted behaviour.
  PLAN §13, last row: "WER looks great, corpus is wrong" — this is the mirror image.

**Escalate before running the sweep.** What T2 needs is a short span transcribed
verbatim *from the audio*, not the polished delivery document.

## Second blocker — the audio does not match the reference

`resource/audios/videoplayback.m4a` (846 s) is **a different episode** from the docx.
Transcribing it yields:

> BIÊN TẬP VIÊN NGỌC HÀ VÀ NHÀ VĂN HOÀNG ANH TÚ XIN KÍNH CHÀO QUÝ VỊ VÀ CÁC BẠN

whereas the docx episode is MC **Thanh Huyền** with nhà văn **Di Li**. The §4.1 clip has
to come from the same episode as the reference, so neither supplied file can be paired
with the other as-is.

## What did run — engine behaviour on real VOV audio

Not a gate result. Recorded because it is the first measurement on real client material.

| | |
|---|---|
| audio | 846.7 s (14:07), m4a |
| VAD | 61 segments, 830.7 s speech, **98 % coverage** (well above the §3 70 % floor) |
| words / utterances | 3426 / 31 |
| speaker clusters | 11 |
| ASR | ~26× realtime |
| diarization | ~5× realtime — the slow stage, as §3 predicts |
| **total** | **5.1× realtime** |
| **peak RSS** | **861 MB** (T1 budget 2 GB) |
| hotwords | 15 terms active, sha `b4acf98843ce…` recorded on the transcript row |

### Engine facts that differ from PLAN §2

* **Output is UPPERCASE**, not lowercase as §2 states. Nothing in the pipeline changes it
  — that would be a §0.1 violation. It matters for T2 because `run_pilot.py` lowercases
  the *reference* only.
* **`bpe_vocab=bpe.model` does not work.** sherpa-onnx 1.13.8 wants a text vocab
  (`<piece> <score>` per line) and fails with "Each line in vocab should contain two
  items". `asr.ensure_bpe_vocab()` exports one from the sentencepiece model; without it
  hotwords cannot load at all.

### Utterance granularity — worth an owner decision

31 utterances over 14 minutes means paragraphs averaging ~27 s. That follows from two
PLAN rules interacting: §2.2 sets each word's `end` to the next word's `start`, so the
gap between consecutive words inside a VAD segment is **0 by construction**, and §3's
"new utterance when gap > 0.5 s" therefore only ever fires at a VAD segment boundary or
a speaker change.

The reference docx is far finer-grained (280 lines). Making the Word export match would
mean splitting on something other than a real pause — punctuation the engine does not
emit, or a fixed length. That is a change to corpus semantics, so it is deliberately
**not** done here. Options, if finer paragraphs are wanted: lower `VAD_MAX_SEGMENT_S`
from 25 s, or split on diarization boundaries inside a segment.

## Gate (PLAN §4.2) — all four still unmeasured

| Check | Passes if | Result |
|---|---|---|
| **Verbatim** | Fillers appear where the reference has them; filler recall ≥ 0.85 | **blocked — reference not verbatim** |
| **Diarization** | MC, guest and ≥ 2 vox-pop voices on separate clusters | unmeasured (11 clusters found; no labelled truth to check against) |
| **Timestamps** | Clicking a word plays it within ~200 ms | click-to-play works in the UI; not measured against truth |
| **Names/terms** | *Thanh Huyền, Di Li, quản chồng, giữ lửa* survive with hotwords | unmeasured — wrong episode |

## Decision

- [ ] Supply a verbatim 2-minute reference **from the same episode as the audio**
- [ ] 30M vs 150M:
- [ ] Chosen knobs written to the `settings` table:
- [ ] **Owner sign-off on verbatim:**
