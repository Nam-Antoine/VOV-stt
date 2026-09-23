# VN-STT Corpus Web App — Implementation Plan for Claude Code

**Prepared:** 22 Sep 2026 · **For:** Claude Code (Opus) · **Owner:** Vũ Tuấn
**Engine:** `hynt/Zipformer-30M-RNNT-6000h` via `sherpa-onnx`, CPU only
**Target host:** 4 vCPU / 6 GB RAM Linux VPS (no GPU)

> Drop this file into the repo root as `PLAN.md`. The `CLAUDE.md` block in §12 goes in the
> repo root too. Work the tasks in §11 **in order** — the pilot gate (T2) must pass before
> any web code is written.

---

## 0. Read this first — the three non-negotiables

### 0.1 This is a linguistic corpus, not a readable transcript
Output must be **verbatim**: fillers (*à, ừ, thì, là, ờ, ừm*), repetitions, false starts,
stutters, dialect forms — all kept. The corpus feeds conceptual-metaphor analysis where the
exact lexical choice is the data. **Any code path that "cleans", "normalises", "smooths",
or "improves" text is a bug.** No post-processing that removes tokens. No LLM rewrite pass.
No dedup of repeated words. If output looks messy, that is correct.

### 0.2 The raw engine JSON is the immutable master record
Every downstream artefact (DB rows, EAF, TXT, CSV) is *regenerated* from the raw JSON.
The raw JSON is written once, never edited, and never overwritten by a re-run — a re-run
creates a new `transcripts` row with a new file. Human corrections live in a separate
layer (`utterances.text_verified`), never in the raw file.

### 0.3 Licensing and legal — not yours to decide, but you must not paper over it
- `hynt/Zipformer-30M-RNNT-6000h` is **CC BY-NC-ND 4.0**. Non-commercial. No derivatives
  (no fine-tuning, no re-export under our name). This is a paid client project. Pilot use
  is fine; **production billing requires written permission from the author (`hynt` on
  Hugging Face)**. Put a `LICENSE-NOTICE.md` in the repo stating this. Do not remove it.
- Audio stays in Vietnam: self-hosting solves the Decree 13/2023 cross-border question that
  the ElevenLabs route raised. If the optional second engine (ElevenLabs Scribe) is ever
  enabled, that question reopens — it is behind a feature flag, off by default.
- Vox-pop voices are identifiable private individuals. Don't build speaker-ID features that
  try to name them; speaker labels are per-episode cluster IDs plus a free-text label the
  verifier types.

---

## 1. What we are building

A self-hosted web app that:

1. Ingests VOV2 *Đàn bà 30+* episodes (upload, URL, or watch-folder) — ~129 episodes,
   ~15 min each, ~32 h total, ongoing after backlog.
2. Runs a CPU pipeline: `ffmpeg → VAD segmentation → Zipformer ASR (word timestamps) →
   speaker diarization → merge → raw JSON`.
3. Stores everything in Postgres, exposes a REST API.
4. Gives verifiers a browser UI: audio player, click-a-word-to-hear-it, inline correction,
   speaker relabelling, low-confidence highlighting, keyterm/hotword management.
5. Exports per episode: raw JSON, verified JSON, ELAN `.eaf`, plain `.txt` (one utterance
   per line with speaker), word-level `.csv`, `.srt`.
6. Runs as `docker compose up` on the VPS; deploys from the git repo.

**Not in v1:** auth beyond per-user accounts (off by default), multi-tenant, GPU paths, streaming
mic input, LLM anything, automatic scraping of vovlive.vn (manual URL ingest only; see §9).

---

## 2. Engine facts (verified 22 Sep 2026)

| Item | Value |
|---|---|
| Model | ZipFormer ~30M params, RNN-T loss, PyTorch + k2 → ONNX export |
| Files (HF repo root) | `encoder-epoch-20-avg-10.{onnx,int8.onnx}`, `decoder-epoch-20-avg-10.{onnx,int8.onnx}`, `joiner-epoch-20-avg-10.{onnx,int8.onnx}`, `bpe.model`, `config.json`, `jit_script.pt` |
| **`config.json` is not JSON** | It is the **tokens.txt** file (23 kB). Download it and save as `tokens.txt`. First line should be `<blk> 0`. HF's "Invalid JSON" warning is expected. |
| Ignore | `jit_script.pt` (flagged "suspicious" pickle; not needed — we use ONNX) |
| Runtime | `pip install sherpa-onnx` (Apache-2.0). Loader = `sherpa_onnx.OfflineRecognizer.from_transducer(...)` |
| Author's own settings | `num_threads=2, sample_rate=16000, feature_dim=80, blank_penalty=0.25, decoding_method="greedy_search" \| "modified_beam_search", max_active_paths=4` |
| Speed | 12 s audio → 0.3 s on a 2-vCPU HF CPU Space ≈ **40× realtime**. Full 32 h backlog ≈ 1 h of ASR compute. Diarization is the slow part (~5–10× realtime). |
| Output | Lowercase, **no punctuation, no casing**. That's fine for a corpus; verifiers add punctuation only if the corpus conventions say so. |
| Timestamps | `result.tokens` + `result.timestamps` (per BPE token, seconds). Word starts are tokens beginning with `▁`. Vietnamese is monosyllabic-orthographic → each `▁`-token group ≈ one syllable-word. |
| Confidence | `result.ys_log_probs` (per token) when available in the installed version; else omit. |
| Hotwords | sherpa-onnx transducer supports contextual biasing: `hotwords_file`, `hotwords_score`, `modeling_unit="bpe"`, `bpe_vocab=bpe.model`. **Requires `decoding_method="modified_beam_search"`.** This is our equivalent of Scribe "keyterms". |
| Reported WER | VLSP2025 public 7.97 / VLSP2023 public 10.40 (vs ChunkFormer 15.55 / 16.15, PhoWhisper-large 16.14 / 16.83). Conversational radio will be worse; the pilot measures reality. |
| ⚠ Verbatim risk | Model card: training labels were "refined using Whisper". Whisper-style labels tend to drop fillers. **Filler recall is unknown until the pilot in §4.** |
| Newer sibling | The author's demo Space also loads `hynt/sherpa-onnx-zipformer-150m-vi-2026-09-09` (592 MB encoder, `epoch-11-avg-2`). Still CPU-feasible on 6 GB. A/B it in the pilot. Check its license separately. |

### 2.1 Reference loader (from the author's demo Space, adapted)

```python
import sherpa_onnx

def load_recognizer(model_dir: str, *, int8: bool = True, threads: int = 3,
                    hotwords_file: str | None = None, hotwords_score: float = 1.5):
    sfx = ".int8.onnx" if int8 else ".onnx"
    kwargs = dict(
        tokens=f"{model_dir}/tokens.txt",          # the file HF calls config.json
        encoder=f"{model_dir}/encoder-epoch-20-avg-10{sfx}",
        decoder=f"{model_dir}/decoder-epoch-20-avg-10{sfx}",
        joiner=f"{model_dir}/joiner-epoch-20-avg-10{sfx}",
        num_threads=threads,
        sample_rate=16000,
        feature_dim=80,
        blank_penalty=0.25,                         # author's default; see §4.3
        decoding_method="modified_beam_search",     # required for hotwords
        max_active_paths=4,
    )
    if hotwords_file:
        kwargs.update(hotwords_file=hotwords_file, hotwords_score=hotwords_score,
                      modeling_unit="bpe", bpe_vocab=f"{model_dir}/bpe.model")
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)

def transcribe_segment(rec, samples_f32, sr=16000):
    s = rec.create_stream()
    s.accept_waveform(sr, samples_f32)
    rec.decode_stream(s)
    r = s.result
    return {"text": r.text, "tokens": list(r.tokens), "timestamps": list(r.timestamps),
            "logprobs": list(getattr(r, "ys_log_probs", []) or [])}
```

### 2.2 Token → word roll-up

```python
def tokens_to_words(tokens, timestamps, logprobs, offset_s, seg_end_s):
    words, cur = [], None
    for i, (tok, t) in enumerate(zip(tokens, timestamps)):
        lp = logprobs[i] if i < len(logprobs) else None
        if tok.startswith("▁") or cur is None:
            if cur: words.append(cur)
            cur = {"text": tok.lstrip("▁"), "start": offset_s + t, "end": None, "lp": [lp]}
        else:
            cur["text"] += tok
            cur["lp"].append(lp)
    if cur: words.append(cur)
    for a, b in zip(words, words[1:]):
        a["end"] = b["start"]
    if words: words[-1]["end"] = offset_s + seg_end_s
    for w in words:
        lps = [x for x in w.pop("lp") if x is not None]
        w["conf"] = float(sum(lps) / len(lps)) if lps else None  # mean log-prob; lower = worse
    return words
```

Word `end` = next word's `start` is an approximation (RNN-T emits at token *start*).
It is good enough for click-to-play in ELAN/UI (±200 ms target). Do not try to be cleverer.

---

## 3. Pipeline design

```
audio file (mp3/m4a/wav)
  │  ffmpeg -i in -ac 1 -ar 16000 -f wav -acodec pcm_s16le    → episode.16k.wav (kept)
  ▼
Silero VAD (sherpa_onnx.VoiceActivityDetector, silero_vad.onnx)
  │  → speech segments; pad each by 0.35 s both sides, merge if gap < 0.3 s,
  │    hard-split any segment > 25 s at the lowest-energy point
  │  ⚠ VAD must never *drop* speech. Short isolated fillers ("à", "ừ") are exactly what
  │    aggressive VAD eats. Use threshold ≈ 0.3, min_speech 0.1 s, min_silence 0.4 s,
  │    and log total speech seconds vs file duration. If speech < 70 % of duration on a
  │    radio talk show, VAD is too aggressive → lower threshold.
  ▼
Zipformer ASR per segment (sequential; one recognizer instance per worker process)
  │  → words[] with absolute timestamps + conf
  ▼
Speaker diarization on the whole file (sherpa_onnx.OfflineSpeakerDiarization)
  │  segmentation: pyannote/segmentation-3.0 ONNX (csukuangfj/sherpa-onnx-pyannote-segmentation-3-0)
  │  embedding:    3D-Speaker or WeSpeaker ONNX (csukuangfj/speaker-embedding-models)
  │  clustering:   num_clusters=0 (auto), threshold tune 0.5–0.9 in pilot
  │  min_duration_on=0.3, min_duration_off=0.5
  │  → segments[] {start, end, speaker:int}
  ▼
Merge: each word gets speaker = diarization segment with max overlap (else nearest, else -1)
  ▼
Utterances: consecutive words, same speaker, gap ≤ 0.5 s → one utterance
  ▼
raw JSON (schema §5) → disk (immutable) → DB rows → exports
```

**Why VAD-split instead of feeding 15 min at once:** non-streaming Zipformer attention
memory grows with length; 15 min in one shot is a 6 GB-box OOM risk and gives worse
timestamps. Segments ≤ 25 s are the normal way sherpa-onnx is used for long audio
(`sherpa-onnx-vad-with-offline-asr`).

**Threads on a 4-vCPU box:** one worker process; ASR `num_threads=3`; diarization runs
after ASR, not concurrently. `OMP_NUM_THREADS=3`. Don't run two episodes in parallel.

**Overlapping speech:** expected in vox-pop segments. No engine handles it. The merge step
assigns the dominant speaker; the UI lets the verifier split/relabel. Do not tune around it.

---

## 4. Pilot gate — must pass before T3 starts

### 4.1 Ground truth
`TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx` is a hand-verified transcript of one episode
(MC Thanh Huyền + nhà văn Di Li + 4 vox-pop women + 4 vox-pop voices later). Locate that
episode's audio on vovlive.vn / vtcnews.vn, and cut a **2-minute clip that contains both
studio dialogue and a vox-pop segment** (the "Ý kiến 1–4" block near the start is ideal).

### 4.2 Pass criteria — all four
| Check | Passes if |
|---|---|
| **Verbatim** | Fillers *à, ừ, thì, là, ờ* appear where the docx has them. Repetitions ("không cần phải quản nữa. Không cần phải quản nữa.") and false starts survive. Compute **filler recall** separately from WER: `fillers_in_hyp / fillers_in_ref` over the set {à, ừ, ờ, ừm, thì, là, ấy, nhé, đấy}. Target ≥ 0.85. |
| **Diarization** | MC, guest, and ≥ 2 distinct vox-pop voices land on separate cluster IDs. |
| **Timestamps** | Clicking a word in the UI (or ELAN) plays that word within ~200 ms. |
| **Names/terms** | *Thanh Huyền, Di Li, quản chồng, giữ lửa* come through with hotwords loaded (compare with/without). |

Also report plain WER (use `jiwer`) with **no normalisation** beyond lowercasing and
stripping punctuation from the reference — because the model emits neither.

### 4.3 Knobs to sweep in the pilot (script, not by hand)
- `blank_penalty` ∈ {0.0, 0.25, 0.5, 0.75} — higher = fewer deletions = better filler recall,
  but more insertions. Pick by filler-recall-at-acceptable-WER, **not** by WER alone.
- `decoding_method` greedy vs modified_beam_search (beam 4) — beam is required for hotwords.
- `int8` vs fp32 encoder — int8 is 3× smaller; check it doesn't cost filler recall.
- 30M vs the 150M sibling.
- Diarization `threshold` ∈ {0.5, 0.6, 0.7, 0.8, 0.9}.
- VAD `threshold` ∈ {0.2, 0.3, 0.5}.

Write results to `pilot/RESULTS.md` with sample output pasted in. **If verbatim fails on
every setting, stop and escalate — do not proceed to the web app on this engine.**

---

## 5. Raw JSON schema (`schema_version: 1`)

```jsonc
{
  "schema_version": 1,
  "episode_id": "uuid",
  "source": { "filename": "ep042.mp3", "url": "https://vovlive.vn/...", "sha256": "…" },
  "audio": { "duration_s": 901.4, "sample_rate": 16000, "channels": 1 },
  "engine": {
    "name": "zipformer-30m-rnnt-6000h", "hf_repo": "hynt/Zipformer-30M-RNNT-6000h",
    "files": { "encoder": "encoder-epoch-20-avg-10.int8.onnx", "...": "..." },
    "sherpa_onnx_version": "1.x.y",
    "params": { "decoding_method": "modified_beam_search", "max_active_paths": 4,
                "blank_penalty": 0.25, "hotwords_score": 1.5, "hotwords_sha256": "…" }
  },
  "vad": { "model": "silero_vad.onnx", "threshold": 0.3, "min_silence_s": 0.4, "pad_s": 0.35,
           "segments": [[0.52, 18.90], [19.30, 41.02]] },
  "diarization": { "segmentation": "pyannote-segmentation-3.0", "embedding": "3dspeaker-…",
                   "threshold": 0.7, "num_clusters": 0,
                   "segments": [{"start": 0.5, "end": 18.9, "speaker": 0}] },
  "words": [
    { "i": 0, "text": "kính", "start": 0.52, "end": 0.71, "conf": -0.12, "speaker": 0 },
    { "i": 1, "text": "chào", "start": 0.71, "end": 0.95, "conf": -0.04, "speaker": 0 }
  ],
  "utterances": [
    { "i": 0, "speaker": 0, "start": 0.52, "end": 18.9, "word_ids": [0, 1, 2], 
      "text": "kính chào quý vị và các bạn" }
  ],
  "created_at": "2026-09-22T09:00:00+07:00"
}
```

Always `json.dump(..., ensure_ascii=False)` and open files with `encoding="utf-8"`.
Diacritics turning into `ạ` means someone forgot — treat as a test failure.

---

## 6. Stack

| Layer | Choice | Why |
|---|---|---|
| Backend API | **Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2** | Same language as the engine; one image for api + worker |
| Worker | Same image, `python -m app.worker` — polls Postgres jobs table with `SELECT … FOR UPDATE SKIP LOCKED` | No Redis on a 6 GB box; DB-as-queue is enough for 1 worker |
| DB | **Postgres 16** (docker) | JSONB for words, full-text search over corpus later |
| Engine deps | `sherpa-onnx`, `numpy`, `soundfile`, `ffmpeg` (apt), `sentencepiece` | |
| Frontend | **React 18 + TypeScript + Vite**, TanStack Query, Tailwind, `wavesurfer.js` for the player | Static build; no SSR needed |
| Reverse proxy | **Caddy** (auto-TLS) → `/api/*` → api:8000, everything else → static `web/dist` | One config file |
| Storage | Local volume `/data`: `audio/`, `raw/`, `exports/`, `models/` | Back up `/data/raw` — it's the master record |
| Auth | Per-user accounts (admin/editor), scrypt hashes, signed session cookie; admins create accounts, no sign-up | Public on vovstt.io.vn |

No LLM API calls anywhere in the pipeline. `anthropic`/`openai` packages are not dependencies.

---

## 7. Repo layout

```
vn-stt-corpus/
├── PLAN.md                      ← this file
├── CLAUDE.md                    ← §12
├── LICENSE-NOTICE.md            ← §0.3 wording
├── docker-compose.yml
├── Caddyfile
├── .env.example
├── Makefile                     ← make dev / make pilot / make deploy / make export EP=…
├── models/                      ← .gitignored; populated by scripts/download_models.py
├── scripts/
│   ├── download_models.py       ← HF hub download; renames config.json → tokens.txt; sha256 check
│   ├── fetch_episode.py         ← URL → /data/audio (ffmpeg / yt-dlp); records source url + sha
│   └── backfill.py              ← enqueue transcribe jobs for every audio file without a transcript
├── pilot/
│   ├── clip_2min.wav            ← .gitignored
│   ├── reference.txt            ← from the docx, one utterance per line, "SPEAKER<TAB>text"
│   ├── run_pilot.py             ← sweeps §4.3, writes RESULTS.md
│   └── RESULTS.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py              ← FastAPI app, routers, static fallback
│       ├── config.py            ← pydantic-settings; all knobs from env
│       ├── db.py, models.py, schemas.py
│       ├── api/
│       │   ├── episodes.py, jobs.py, transcripts.py, utterances.py,
│       │   ├── speakers.py, hotwords.py, exports.py, auth.py
│       ├── worker.py            ← job loop
│       ├── pipeline/
│       │   ├── audio.py         ← ffmpeg normalise, sha256, duration
│       │   ├── vad.py           ← silero via sherpa_onnx
│       │   ├── asr.py           ← §2.1 / §2.2
│       │   ├── diarize.py
│       │   ├── merge.py         ← words↔speakers, utterances
│       │   ├── hotwords.py      ← DB table → hotwords.txt (one term per line) + sha
│       │   └── run.py           ← orchestrates one episode end-to-end, writes raw JSON
│       ├── exports/
│       │   ├── eaf.py           ← ELAN 3.0, one tier per speaker label (adapted from the Sept-20 guide)
│       │   ├── txt.py, csv.py, srt.py, json_verified.py
│       └── tests/
│           ├── test_tokens_to_words.py
│           ├── test_merge.py
│           ├── test_eaf_roundtrip.py
│           ├── test_no_normalisation.py   ← asserts a hyp with "à à ừ thì" survives every export unchanged
│           └── fixtures/
└── web/
    ├── package.json, vite.config.ts, tailwind.config.js
    └── src/
        ├── api/                 ← typed client (generated from OpenAPI or hand-written)
        ├── pages/
        │   ├── Episodes.tsx     ← list, status chips, upload/URL ingest, bulk enqueue
        │   ├── Episode.tsx      ← player + transcript editor (the core screen)
        │   ├── Jobs.tsx         ← queue, retries, logs
        │   ├── Hotwords.tsx     ← CRUD; "re-run affected episodes" button
        │   └── Exports.tsx
        └── components/
            ├── WaveformPlayer.tsx   ← wavesurfer; seeks on word click; loop-utterance
            ├── TranscriptEditor.tsx ← utterances grouped by speaker; contenteditable words
            ├── SpeakerLegend.tsx    ← rename cluster 0 → "MC Thanh Huyền"; colour per speaker
            └── ConfidenceToggle.tsx ← highlight words with conf below percentile
```

---

## 8. Database schema

```sql
episodes (
  id uuid pk, slug text unique, title text, source_url text, air_date date,
  audio_path text, audio_sha256 text, duration_s numeric,
  status text check (status in ('ingested','queued','processing','transcribed','verifying','verified','failed')),
  created_at timestamptz, updated_at timestamptz
)

jobs (
  id uuid pk, episode_id uuid fk, kind text check (kind in ('transcribe','export')),
  status text check (status in ('queued','running','done','failed')),
  attempts int default 0, max_attempts int default 3,
  params jsonb, error text, log text,
  locked_at timestamptz, started_at timestamptz, finished_at timestamptz, created_at timestamptz
)
-- worker: UPDATE jobs SET status='running', locked_at=now() WHERE id = (
--   SELECT id FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;

transcripts (                      -- one per engine run; immutable
  id uuid pk, episode_id uuid fk, engine text, engine_version text, params jsonb,
  hotwords_sha256 text, raw_json_path text, is_current bool default true,
  wer_vs_reference numeric null,   -- filled by pilot only
  created_at timestamptz
)

words (                            -- derived from raw JSON; rebuildable
  transcript_id uuid fk, i int, text text, start_s numeric, end_s numeric,
  conf numeric null, speaker int, primary key (transcript_id, i)
)
create index on words using gin (to_tsvector('simple', text));  -- corpus search later

utterances (                       -- the human-editable layer
  id uuid pk, transcript_id uuid fk, i int, speaker int,
  start_s numeric, end_s numeric,
  text_asr text not null,          -- frozen copy from raw JSON
  text_verified text null,         -- null = untouched
  verified_by text null, verified_at timestamptz null,
  flags text[] default '{}'        -- e.g. {'overlap','unclear','music'}
)

utterance_edits (                  -- audit log, append-only
  id bigserial pk, utterance_id uuid fk, before text, after text, editor text, at timestamptz
)

speakers (
  episode_id uuid, cluster int, label text, primary key (episode_id, cluster)
)

hotwords (
  id serial pk, term text unique, weight numeric default 1.0, note text, active bool default true,
  created_at timestamptz
)
-- seed: Đàn bà 30+, VOV2, Thanh Huyền, Di Li, Hoàng Anh Tú, Đỗ Anh Vũ,
--       quản chồng, giữ chồng, giữ lửa, ngoại tình, tâm sự, hôn nhân, chung thủy, ly hôn, gia đình

settings (key text pk, value jsonb)   -- pipeline knobs chosen in the pilot (blank_penalty, thresholds…)
```

---

## 9. API surface (all under `/api`, JSON, cookie auth)

```
POST   /auth/login                       {username, password}
GET    /episodes?status=&q=              list
POST   /episodes/upload                  multipart file → ingest job
POST   /episodes/from-url                {url, title?, air_date?} → fetch + ingest
GET    /episodes/{id}                    episode + current transcript summary + speakers
POST   /episodes/{id}/transcribe         enqueue (params override optional)
DELETE /episodes/{id}                    only if no verified utterances; keeps raw JSON on disk

GET    /jobs?status=                     queue view
POST   /jobs/{id}/retry
GET    /jobs/{id}/log

GET    /transcripts/{id}                 words + utterances + speakers (what the editor loads)
GET    /transcripts/{id}/raw             the immutable JSON file
GET    /transcripts/{id}/audio           range-request streaming of episode.16k.wav (or original)

PATCH  /utterances/{id}                  {text_verified?, speaker?, flags?, start_s?, end_s?}
POST   /utterances/{id}/split            {at_word_i}
POST   /utterances/{id}/merge-next
POST   /utterances/{id}/revert           text_verified = null

PUT    /episodes/{id}/speakers/{cluster} {label}

GET    /hotwords            POST /hotwords            PATCH /hotwords/{id}        DELETE /hotwords/{id}
POST   /hotwords/rerun-all               enqueue transcribe for every episode with no verified utterances

GET    /episodes/{id}/export.{json|verified.json|eaf|txt|csv|srt}
GET    /exports/corpus.zip?tier=verified|all
GET    /stats                            episodes by status, hours transcribed, hours verified, mean conf
```

**Ingest from URL:** `scripts/fetch_episode.py` tries a direct media URL first, then `yt-dlp`
for page URLs. vovlive.vn episode pages embed an mp3 — handle that case. No crawler in v1;
the "ongoing service" path is: someone pastes the new episode URL → same pipeline. A
scheduled poller is a v2 item and needs a robots/ToS check first.

---

## 10. Frontend — the Episode screen is the product

Layout: waveform + play controls pinned top; transcript below, grouped into utterances,
each with a speaker chip (coloured, click to relabel) and a timestamp.

Must-haves:
- **Click a word → seek and play from that word.** Space = play/pause. `[`/`]` = previous/next
  utterance. `L` = loop current utterance. This is what makes verification 2× faster.
- Words are inline-editable; a changed utterance turns amber until saved; save on blur
  (PATCH) with optimistic update; `Ctrl+Z` reverts to `text_asr`.
- "Show confidence" toggle: words below the 15th percentile of `conf` get a dotted underline.
- Speaker legend: rename cluster → label once, applies to whole episode.
- Flags per utterance: overlap / unclear / music-or-jingle / not-speech.
- Progress: "142 / 388 utterances verified" and a "mark episode verified" button.
- Read-only diff view: `text_asr` vs `text_verified` per utterance (for QA and for the
  hotword feedback loop — recurring corrections → add to hotwords).
- Never auto-capitalise, auto-punctuate, or spell-check the editable text (disable browser
  `spellcheck`, `autocapitalize`, `autocorrect` on the editor).

Episodes page: status chips, bulk "enqueue all ingested", upload dropzone, URL box.
Jobs page: running job with live log tail (poll every 2 s), failed jobs with retry.

---

## 11. Task list — do in this order

**T0 — Scaffold (½ day)**
- [ ] Repo, `docker-compose.yml` (db, api, worker, caddy), `.env.example`, `Makefile`
- [ ] `scripts/download_models.py`: pulls the 6 ONNX files + `bpe.model` + `config.json`→`tokens.txt`
      from `hynt/Zipformer-30M-RNNT-6000h`; silero VAD; pyannote segmentation ONNX; one
      speaker-embedding ONNX. Writes `models/MANIFEST.json` with sha256s. Idempotent.
- [ ] `LICENSE-NOTICE.md`, `CLAUDE.md`

**T1 — Engine spike (½ day)** — plain scripts, no web
- [ ] `backend/app/pipeline/{audio,vad,asr,diarize,merge,run}.py` runnable as
      `python -m app.pipeline.run --audio x.mp3 --out x.json`
- [ ] Unit tests: `tokens_to_words`, merge, `test_no_normalisation`
- [ ] Prints RTF (realtime factor) and peak RSS. Must run in < 2 GB RSS.

**T2 — PILOT GATE (1 day)** ← stop here until it passes
- [ ] Obtain the docx episode's audio; cut 2-min clip; build `pilot/reference.txt`
- [ ] `pilot/run_pilot.py` sweeps §4.3, computes WER + filler recall + diarization purity,
      writes `pilot/RESULTS.md` with pasted samples
- [ ] Chosen knobs written to `settings` seed. Decision recorded: 30M vs 150M.
- [ ] **Owner sign-off on verbatim.** If fail → escalate; do not continue.

**T3 — Backend (2 days)**
- [ ] Alembic schema §8, models, seed hotwords
- [ ] Worker loop with SKIP LOCKED, retries with backoff, log capture to `jobs.log`
- [ ] Ingest (upload + from-url), transcribe job, raw JSON → words/utterances rows
- [ ] All endpoints in §9; OpenAPI at `/api/docs`
- [ ] Exports: json, verified.json, eaf, txt, csv, srt; `test_eaf_roundtrip` opens the EAF
      with `xml.etree` and asserts tier count = speaker count and every annotation has slots

**T4 — Frontend (2 days)**
- [ ] Episodes, Episode (§10), Jobs, Hotwords, Exports pages
- [ ] Keyboard shortcuts; spellcheck/autocorrect disabled on editor
- [ ] `npm run build` output served by Caddy

**T5 — Deploy (½ day)**
- [ ] `make deploy` = `git pull && docker compose build && docker compose up -d && alembic upgrade head`
- [ ] Healthcheck `/api/health` reports db + models present + worker heartbeat
- [ ] Nightly `tar` of `/data/raw` + `pg_dump` to a second disk/bucket (raw JSON is the master record)
- [ ] `scripts/backfill.py` to enqueue the 129-episode backlog; expect ~1 h ASR + ~4 h
      diarization on 4 vCPU — run overnight; check zero failed jobs before declaring done

**T6 — Optional, after backlog is running**
- [ ] Second-engine consensus: `engine='elevenlabs-scribe-v2'` behind `ENABLE_SCRIBE=false`.
      Data-residency decision from client required first. Diff tier in EAF for disagreements.
- [ ] Corpus search page over `words` (tsvector, `simple` config — no stemming).
- [ ] Scheduled poller for new episodes.

---

## 12. `CLAUDE.md` (put in repo root)

```markdown
# CLAUDE.md — vn-stt-corpus

Read PLAN.md first. Key rules:

1. VERBATIM. Never add code that removes, dedupes, normalises, capitalises, punctuates,
   or "cleans" transcript text. Fillers and repetitions are the data. `tests/test_no_normalisation.py`
   must stay green.
2. Raw engine JSON under /data/raw is immutable. New run = new file + new transcripts row.
3. Vietnamese text: always `ensure_ascii=False`, `encoding="utf-8"`. Check exports for `\u1e`.
4. The model's `config.json` IS `tokens.txt`. Don't try to parse it as JSON.
5. Hotwords need `decoding_method="modified_beam_search"`. Don't switch to greedy to "speed up".
6. One worker process, ASR num_threads=3, no parallel episodes (4 vCPU / 6 GB box).
7. No LLM calls in the pipeline or the app. No anthropic/openai packages.
8. Licence: model is CC BY-NC-ND 4.0. Keep LICENSE-NOTICE.md. Don't fine-tune or re-export.
9. Don't build speaker identification of real people; labels are per-episode cluster → free text.
10. Do not start T3+ until pilot/RESULTS.md shows the verbatim gate passed and is signed off.

Commands: `make dev`, `make test`, `make pilot`, `make deploy`, `make export EP=<slug>`.
```

---

## 13. Things that will bite you

| Symptom | Cause / fix |
|---|---|
| `sherpa_onnx` fails to load tokens | You passed `config.json`. Rename to `tokens.txt`; first line `<blk> 0`. |
| Text suspiciously clean, no "à/ừ" | Either the model (pilot fail) or VAD ate short segments (lower threshold, add padding). Diff against the docx. |
| Diacritics as `ạ` | Missing `ensure_ascii=False`. |
| Words glued together / spacing wrong | You split on spaces instead of on `▁` tokens. |
| Hotwords have no effect | Decoding is greedy. Must be `modified_beam_search`; also `modeling_unit="bpe"` + `bpe_vocab`. |
| Too many speaker clusters | Raise diarization threshold; also `min_duration_on`. Vox-pop montage segments will always be messy — flag, don't tune forever. |
| Two speakers merged | Lower threshold. |
| OOM on worker | You fed a whole episode without VAD split, or ran two jobs in parallel. |
| Timestamps drift late in file | Segment offsets not added, or ffmpeg resample changed duration — always compute offsets from the 16 kHz WAV, not the mp3. |
| WER looks great, corpus is wrong | You normalised the hypothesis before scoring. Score raw. Report filler recall separately. |

---

## 14. Decision log (why this and not the earlier plans)

- **20 Sep state file:** self-host ChunkFormer (BY-NC, 110M) or PhoWhisper-medium. Both
  need more CPU than Zipformer-30M and score worse on VLSP; ChunkFormer has the same NC
  licence problem.
- **20 Sep PDF guide (v1.0):** ElevenLabs Scribe v2. Cheap and verbatim-capable, but audio
  leaves Vietnam (Decree 13 flag) and requires training opt-out hygiene. Retained as the
  *optional second engine* for consensus — two differently-trained engines is the only way
  to cut verification from 100–160 h to 30–45 h.
- **22 Sep (this plan):** Zipformer-30M via sherpa-onnx as primary. Fits the 4 vCPU/6 GB
  VPS with ~40× realtime, keeps audio in-country, gives word timestamps + hotwords +
  confidence. Unknowns are verbatim recall and the NC-ND licence — both are gates, not
  assumptions.