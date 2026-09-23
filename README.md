# VOV-stt — vn-stt-corpus

[![CI](https://github.com/Nam-Antoine/VOV-stt/actions/workflows/ci.yml/badge.svg)](https://github.com/Nam-Antoine/VOV-stt/actions/workflows/ci.yml)

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

## CPU budget — deviation from CLAUDE.md rule 6

Rule 6 specifies `num_threads=3`. This box runs the `tleducation` stack alongside this
one and was sitting at load ~11 on 4 vCPU, so on the owner's instruction (22 Sep 2026,
*"it takes so much of the CPU … reduce the load"*) the knobs are now:

| Knob | Rule 6 | Here | Where |
|---|---|---|---|
| ASR threads | 3 | **2** | `ASR_NUM_THREADS` |
| Diarization threads | 3 | **2** | `DIAR_NUM_THREADS` |
| `OMP_NUM_THREADS` | 3 | **2** | `docker-compose.yml` |
| worker CPU cap | — | **2.5** | `docker-compose.yml` |
| worker `nice` | — | **10** | `WORKER_NICE` |
| diarization | always | **per-job toggle** | `DIARIZE_BY_DEFAULT` |

Still one worker process and no parallel episodes — that half of rule 6 is untouched.
Diarization is the expensive stage; turning it off roughly halves CPU time per episode
at the cost of speaker labels. Restore the rule-6 values by setting the three thread
counts back to 3 and dropping the `cpus` cap.

## Quick start

```bash
cp .env.example .env            # edit SECRET_KEY
make models                     # ~525 MB of ONNX into ./models
make test                       # unit tests, including the verbatim gate
make dev                        # db + api + worker + caddy
# only with AUTH_ENABLED=true in .env — login is off by default:
docker compose exec api python -m app.users create <you> --admin
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

## CI / CD

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | What it guards |
|---|---|
| **Verbatim gate** | `test_no_normalisation.py`, plus a grep that fails the build if an LLM client package ever lands in `backend/pyproject.toml` (CLAUDE.md rule 7) |
| Backend | `ruff check` + the full pytest suite with coverage |
| Migrations | `alembic upgrade head` against a real Postgres 16, then `downgrade base` and up again, then asserts the §8 hotword seed is present |
| Frontend | `tsc --noEmit` + `vite build`, uploads `web/dist` |
| Images | builds `backend/Dockerfile` and validates `docker compose config` |

The verbatim gate is a separate job on purpose. PLAN §0.1 is a correctness property of
the corpus, not a style rule, so it should be readable as pass/fail on its own line and
set as a required check on `main`.

`.github/workflows/deploy.yml` deploys to the VPS after CI goes green on `main`, or on
demand, once the repository variable `DEPLOY_ENABLED` is `true`. It pulls, rebuilds, migrates, then polls `/api/health` until the API, the DB, all
the model checks *and* the worker heartbeat are good — an API that answers while the worker
is dead would queue jobs forever. On failure it rolls the code back to the previous commit.

It is pull-based rather than a registry push so the ~525 MB model cache and the `/data`
volume survive every release untouched (PLAN §0.2).

**Before the first deploy**, add these repository secrets
(*Settings → Secrets and variables → Actions*):

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | the VPS address |
| `DEPLOY_USER` | ssh user |
| `DEPLOY_SSH_KEY` | private key (PEM) whose public half is in the box's `authorized_keys` |
| `DEPLOY_PATH` | checkout path on the box, e.g. `/ternary/vov-stt` |
| `DEPLOY_PORT` | optional, defaults to 22 |
| `HEALTH_URL` | optional, defaults to `http://localhost:8080/api/health` |

The deploy job targets a `production` environment, so you can require a manual approval
on it in the repo settings. Schema **downgrades are never automated**: migration `0001`
drops every table, which would destroy the corpus, so a rollback restores code only and
says so in the log.

## Layout

See PLAN.md §7. In short: `backend/app/pipeline` is the engine, `backend/app/exports`
turns raw JSON into the six output formats, `backend/app/api` is the §9 surface,
`web/` is the verifier UI, `scripts/` holds the model downloader and ingest helpers, and
`pilot/` holds the T2 gate.
