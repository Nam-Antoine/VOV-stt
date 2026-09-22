# VOV-stt — vn-stt-corpus

A self-hosted verbatim speech corpus for VOV2 *Đàn bà 30+*. CPU-only ASR pipeline,
Postgres, FastAPI, React. See **PLAN.md** for the full design and **CLAUDE.md** for the
rules any contributor (human or model) has to work under.

> **This is a linguistic corpus, not a readable transcript.** Fillers, repetitions,
> false starts and dialect forms are the data. Any code path that "cleans", "normalises"
> or "improves" text is a bug — PLAN §0.1.

> **Licence:** the ASR model is CC BY-NC-ND 4.0 (non-commercial, no derivatives).
> Production billing needs written permission from the author. See LICENSE-NOTICE.md.

## Current state

| Task | State |
|---|---|
| T0 — scaffold, compose, models downloader | done |
| T1 — pipeline runnable end-to-end, unit tests | done |
| **T2 — pilot gate** | **not run — see `pilot/RESULTS.md`; the supplied reference is not verbatim** |
| T3 — backend handlers, worker, exports | done |
| T4 — frontend (upload → transcript → export) | done |
| T5 — deploy, backfill | partial: compose stack runs; no nightly backup yet |

> **T3/T4 were built before T2 passed.** CLAUDE.md rule 10 forbids that. It was done on
> the owner's explicit written instruction (22 Sep 2026) to deliver a working upload →
> transcript web app. The gate is *not* waived: `pilot/RESULTS.md` records why it still
> cannot be scored as PLAN §4.2 specifies, and no claim is made here about filler recall.

## What works end to end

Upload audio in the browser → it is hashed and stored → a queued job transcribes it on
one worker → the transcript appears with speaker chips, click-a-word-to-play, and inline
editing → export as `.docx`, `.txt`, `.csv`, `.srt`, `.eaf`, raw or verified JSON.

Measured on a real 14-minute VOV episode (846 s), 4 vCPU shared box:

| | |
|---|---|
| words / utterances | 3426 / 31 |
| speaker clusters | 11 |
| VAD coverage | 98 % of duration |
| total | **5.1× realtime** (ASR alone ~26×; diarization is the slow stage) |
| peak RSS | **861 MB** (T1 budget: 2 GB) |

## Quick start

```bash
cp .env.example .env            # edit APP_PASSWORD and SECRET_KEY
make models                     # ~64 MB of ONNX into ./models
make test                       # unit tests, including the verbatim gate
make dev                        # db + api + worker + caddy
```

Transcribe one file without the web stack:

```bash
cd backend
python -m app.pipeline.run --audio /path/to/ep042.mp3 --out /path/to/ep042.json \
  --models ../models
```

That prints the realtime factor and peak RSS, and writes the PLAN §5 raw JSON.

## Export formats

Per episode: `.docx`, plain `.txt`, raw `.json`, `verified.json`, ELAN `.eaf`,
word-level `.csv`, `.srt` — plus `exports/corpus.zip` for the whole corpus
(`?tier=verified|all`).

`.docx` is **not** in PLAN §1.5. It was added because the client's reference deliverable
(`resource/docs/*.docx`) is a Word document: speaker heading, then one paragraph per
utterance. It is a *layout* only — the text inside is the same bytes every other export
carries, and `test_no_normalisation.py` holds it to that like the rest.

Every export is regenerated from the raw JSON plus the verified layer. Nothing is cached
and then allowed to drift (PLAN §0.2).

## Layout

See PLAN.md §7. In short: `backend/app/pipeline` is the engine, `backend/app/exports`
turns raw JSON into the six output formats, `backend/app/api` is the §9 surface,
`web/` is the verifier UI, `scripts/` holds the model downloader and ingest helpers, and
`pilot/` holds the T2 gate.
