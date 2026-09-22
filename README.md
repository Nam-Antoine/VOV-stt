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
| **T2 — pilot gate** | **not started; needs owner sign-off before T3** |
| T3–T5 — backend handlers, frontend, deploy | skeletons only |

The API handlers, the worker's job handlers and the UI pages are deliberate stubs: T2 is
a gate, and PLAN §11 says no web code before it passes.

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

Per episode: raw `.json`, `verified.json`, ELAN `.eaf`, plain `.txt`, word-level `.csv`,
`.srt` (PLAN §1.5) — plus `exports/corpus.zip` for the whole corpus.

> The repository description mentions **docx or pdf**. Those are not in PLAN.md §1.5 and
> are not implemented. `.txt` and `.csv` are the formats intended for hand-off to a word
> processor; say so if a real `.docx` deliverable is needed and it can be added.

## Layout

See PLAN.md §7. In short: `backend/app/pipeline` is the engine, `backend/app/exports`
turns raw JSON into the six output formats, `backend/app/api` is the §9 surface,
`web/` is the verifier UI, `scripts/` holds the model downloader and ingest helpers, and
`pilot/` holds the T2 gate.
