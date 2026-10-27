# Đàn bà 30+ Corpus — Implementation Plan (full rerun)

Version 1.0 · 25 Sep 2026 · Supersedes nothing; extends *VOV2 Corpus Transcription Guide v1.0* with Phase 4.

---

## 0. What this is

A pipeline that turns ~129 episodes of the VOV2 radio program *Đàn bà 30+* (~15 min each, ~32 hours total)
into a **verbatim linguistic corpus**, published as:

- one **Google Doc per episode** (plain verbatim text, **no speaker labels**), and
- one **Google Sheet index**, one row per episode, the title cell linking to its Doc (**no Guest or MC columns**).

This plan covers building the pipeline and **re-running every episode from audio**.

### The one rule

**Never clean up the text.** Fillers (*à, ừ, thì, là*), repetitions, false starts, stutters, dialect spellings and
grammatical "errors" are the research data. No step may normalise, correct, re-punctuate, deduplicate or
"tidy" transcript text. If output looks messy, that is the deliverable.

---

## 1. Hard rules (apply to every file in the repo)

| # | Rule |
|---|---|
| R1 | The Scribe call **never** contains `no_verbatim` — not `True`, not `False`. The parameter is absent. A test enforces this. |
| R2 | All JSON is written with `ensure_ascii=False`, all files with `encoding="utf-8"`. |
| R3 | When rebuilding text from Scribe words, keep `type == "spacing"` tokens. Never filter to words and re-join. |
| R4 | Raw Scribe JSON is the master record. Never edit it. Never delete it — a rerun **archives** old outputs. |
| R5 | Human corrections happen only in ELAN (`.eaf`). `.txt`, Docs and Sheet are generated from `.eaf` and can be rebuilt. |
| R6 | Delivered text has **no speaker labels**. `diarize=True` stays on; `speaker_id` lives only in JSON and ELAN tiers. |
| R7 | The Sheet has **no Guest or MC columns**. |
| R8 | Secrets (`.env`, `credentials.json`, `token.json`) are gitignored and never printed or logged. |
| R9 | One code path for backlog and ongoing episodes. No second "quick" script with different parameters. |
| R10 | Every batch step is idempotent, resumable, and never silently skips a file (failures go to `failed.log`). |

---

## 2. Repository layout

```
dan-ba-30-corpus/
├── PLAN.md                    # this file
├── README.md                  # how to run each stage
├── .env                       # ELEVENLABS_API_KEY (gitignored)
├── credentials.json           # Google OAuth desktop client (gitignored)
├── token.json                 # Google OAuth token (gitignored)
├── requirements.txt
├── keyterms.py                # living list of names + domain vocabulary
├── episodes.csv               # manifest + metadata, the ONLY place metadata is edited
├── repo_state.json            # Google folder/sheet/doc ids + text hashes (back this up)
├── gates/                     # human sign-off files (see §4)
├── data/ground_truth/         # hand-verified pilot transcript (docx)
├── audio/                     # ep001.mp3 …
├── transcripts_json/          # ep001.json … (master record)
├── elan/                      # ep001.eaf …
├── transcripts_txt/           # ep001.txt … (no labels)
├── archive/<YYYY-MM-DD>/      # previous outputs moved here on a rerun
├── reports/                   # pilot_report.md, run summaries
├── failed.log
├── cost_log.csv
├── pipeline/
│   ├── config.py
│   ├── build_manifest.py
│   ├── fetch_audio.py
│   ├── transcribe.py
│   ├── to_eaf.py
│   ├── export_text.py
│   ├── sync_repository.py
│   ├── pilot_check.py
│   └── run_all.py             # single entrypoint, runs stages in order, respects gates
└── tests/
```

`requirements.txt`: `elevenlabs`, `python-dotenv`, `google-api-python-client`, `google-auth-oauthlib`,
`google-auth-httplib2`, `python-docx`, `pytest`.

---

## 3. Stages

### Stage 0 — Preflight (`run_all.py preflight`)

Checks, each printed PASS/FAIL, stop on any FAIL:

- `.env` has `ELEVENLABS_API_KEY`; `credentials.json` exists.
- `gates/training_optout.png` exists (dated screenshot of ElevenLabs *Improve the models for everyone* disabled).
- `gates/residency_decision.md` exists (written client decision on sending audio to ElevenLabs (US) and storing
  transcripts in Google Drive). **Required before Stage 4, not before the pilot.**
- `gates/google_account.md` names the Google account that owns the repository.
- `pytest` passes.

### Stage 1 — Manifest (`build_manifest.py`)

Build `episodes.csv` from the program listings:

- Listing: `https://vovlive.vn/dan-ba-30-p31.html` (and its paginated pages)
- Mirror with durations: `https://vtcnews.vn/dan-ba-30-al235.html`

Columns: `episode_id,title,air_date,duration,source_url,audio_url,tier,status,verified_by,verified_date`

- `episode_id` = `ep001` … in air-date order, oldest first. IDs are permanent once assigned.
- `tier` defaults to `Reference`; `status` defaults to `Not started`.
- Expected ≈129 rows, Nov 2020 → Aug 2026, durations mostly 14:03–15:00 (outliers 29:37, 16:38, 16:22).
- If an existing `episodes.csv` is present, **merge**: never renumber, never overwrite `tier`, `status`,
  `verified_by`, `verified_date`.
- Print count, date range, and any episodes missing a duration or audio URL.

If the pages need login, block scraping, or the audio URL can't be found reliably: **stop and report**. Do not
work around access controls.

**Gate G1:** human checks the manifest and creates `gates/manifest_ok`.

### Stage 2 — Audio (`fetch_audio.py`)

- Download each `audio_url` to `audio/<episode_id>.mp3`. Skip if the file exists and is non-empty.
- Polite: one request at a time, 2 s delay, 3 retries with backoff, failures to `failed.log`.
- After the run, report files present vs. manifest rows and total duration (via `ffprobe` if available).

### Stage 3 — Pilot (`pilot_check.py`)

Pilot episode: the one matching *Tâm sự: Chiến thuật quản trị chồng*. Ground truth:
`data/ground_truth/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx`.

1. Run Stages 4–6 on the pilot episode only.
2. Prepare ground truth: extract docx text, drop speaker-label lines (`MC Thanh Huyền:`, `Nhà văn Di Li:`,
   `Ý kiến …:`, `Nhân vật chia sẻ:`), drop the conceptual-metaphor table at the end, drop bold formatting.
   Lines like "Mùi vị cuộc sống." / "Phiên bản âm." are transcriber notes for jingles — list them in the report,
   exclude them from scoring.
3. Automatic checks, written to `reports/pilot_report.md`:
   - **Verbatim:** counts of *à, ừ, thì, là, ạ, vâng* in ASR vs. ground truth; any count far below ground truth is a red flag.
   - **Word match:** syllable-level alignment ASR vs. ground truth; report error rate and the 30 largest divergent spans side by side.
   - **Diarization:** number of distinct `speaker_id`s (expect ≥ 4: MC, guest, ≥ 2 vox-pop voices).
   - **Names:** Thanh Huyền, Di Li and keyterm vocabulary spelled correctly.
   - **No labels:** exported `.txt` contains no `:`-terminated speaker prefixes.
4. Include a 2-minute excerpt (studio dialogue + a vox-pop segment) of ASR text next to ground truth.

**Gate G2:** human reads the report, opens `elan/<pilot>.eaf` in ELAN to check timestamps (~200 ms), and creates
`gates/pilot_passed`. If the verbatim check fails, **stop the project here** — engine choice is a project-lead
decision, not something to tune around.

### Stage 4 — Transcribe (`transcribe.py`)

Exact call (from the guide, unchanged):

```python
result = client.speech_to_text.convert(
    file=f,
    model_id="scribe_v2",
    language_code="vie",           # pinned, never auto-detect
    timestamps_granularity="word",
    diarize=True,                  # kept: ELAN needs tiers; labels are dropped only at export
    tag_audio_events=True,
    keyterms=KEYTERMS,
    # DO NOT ADD no_verbatim — it strips the fillers we need. Not even =False.
)
```

- `num_speakers` unset; `diarization_threshold` left at default 0.22 unless the pilot report says otherwise.
- Output `transcripts_json/<id>.json` via `model_dump()`, `ensure_ascii=False`, `indent=2`.
- Skip if the JSON exists. 3 retries with backoff; failures to `failed.log`.
- Append each success to `cost_log.csv` (id, audio seconds, estimated $ at $0.22/hr + $0.05/hr keyterms).
- **Cost guard:** expected total ≈ $8.60. Abort if the running estimate exceeds $12 — something is re-processing.
- Requires `gates/pilot_passed` and `gates/residency_decision.md` for any episode other than the pilot.

`keyterms.py` starts with:

```python
KEYTERMS = [
    "Đàn bà 30+", "VOV2", "Thanh Huyền",
    "Di Li", "Hoàng Anh Tú", "Đỗ Anh Vũ",
    "quản chồng", "giữ chồng", "giữ lửa", "ngoại tình", "tâm sự",
    "hôn nhân", "chung thủy", "ly hôn", "gia đình",
]
```

### Stage 5 — JSON → ELAN (`to_eaf.py`)

- Group consecutive words by `speaker_id`, new utterance on pauses > 0.5 s, one tier per speaker.
- Skip `audio_event` tokens in tiers but keep spacing tokens inside utterance text.
- Media descriptor points to `../audio/<id>.mp3` (relative), MIME `audio/mpeg`.
- **Never overwrite an existing `.eaf`** — it may hold human corrections. Regenerate only with `--force`, which
  first copies the old file to `archive/`.

### Stage 6 — Export plain text (`export_text.py`) — Plan 1, no labels

- Read the `.eaf` (not the JSON — corrections live in ELAN).
- Collect annotations from all speaker tiers, skip tooling tiers (`consensus_flags`), sort by start time.
- New paragraph when the speaker changes or after a pause > 1.5 s. **No speaker names anywhere.**
- Join utterances with a single space; do not alter annotation text in any other way.
- Write `transcripts_txt/<id>.txt`, UTF-8, ending in a newline.

### Stage 7 — Google repository (`sync_repository.py`) — Plan 2

Auth:

- OAuth **desktop** client, scope **only** `https://www.googleapis.com/auth/drive.file`.
- **Not** a service account (no Drive storage quota → Doc creation fails).
- First run opens a browser; afterwards `token.json` refreshes silently. The OAuth app must be *In production*
  (or *Internal* on Workspace) — testing-mode tokens expire after 7 days.

Behaviour:

- First run creates folder `Đàn bà 30+ Corpus`, Sheet `Đàn bà 30+ Corpus — Index` inside it (header row frozen).
  IDs saved in `repo_state.json`. If that file is lost, a second repository gets created — so back it up.
- One Doc per episode with a `.txt`, titled `<id> — <title>`, inside the folder. Body = the `.txt`, inserted as
  plain text via the Docs API. Nothing else in the Doc.
- Rewrite a Doc only when the `.txt` SHA-256 changed. Sleep 2 s after each write (Docs limit: 60 writes/min).
- Rebuild the whole Sheet from `episodes.csv` every run (edits made directly in the Sheet are overwritten):

| Column | Value |
|---|---|
| Episode ID | `ep001` |
| Title | `=HYPERLINK("<doc url>", "<title>")` (plain title if no Doc yet; escape `"` as `""`) |
| Air date | from manifest |
| Duration | from manifest, written as `'15:00` so Sheets keeps it as text |
| Source URL | from manifest |
| Tier | Core / Reference |
| Status | Not started / Raw ASR / In review / Verified |
| Verified by | from manifest |
| Verified date | from manifest |
| Syllables | `len(text.split())` — Vietnamese space-separated tokens are syllables |

No Guest column. No MC column. Write with `valueInputOption="USER_ENTERED"`.

- After an episode's `.txt` is first exported, `run_all.py` sets its `status` to `Raw ASR` in `episodes.csv`
  (only if it was `Not started`). Humans move it to `In review` / `Verified`.
- Sharing (folder as Viewer to the client) is done by a human in Drive, not by the script.

### Stage 8 — Ongoing mode (`run_all.py ingest`)

- Re-run Stage 1 in merge mode to pick up new episodes, then Stages 2, 4, 5, 6, 7 for new IDs only.
- Same functions, same parameters, same `keyterms.py`. Suitable for a daily cron job.
- Print a list of new episodes ready for ELAN verification.

---

## 4. Human gates

`run_all.py` checks for these files and stops with a clear message when one is missing.

| Gate | File | Required before |
|---|---|---|
| Training opt-out | `gates/training_optout.png` | Any upload to ElevenLabs |
| Google account | `gates/google_account.md` | Stage 7 |
| Manifest checked | `gates/manifest_ok` | Stage 2 |
| Pilot passed | `gates/pilot_passed` | Stage 4 batch |
| Residency decision | `gates/residency_decision.md` | Stage 4 batch, Stage 7 batch |

Claude Code never creates gate files itself.

---

## 5. The rerun ("redo all the audios")

```
python -m pipeline.run_all rerun
```

1. Move current `transcripts_json/`, `elan/`, `transcripts_txt/`, `failed.log`, `cost_log.csv` into
   `archive/<today>/` (move, not delete). `.eaf` files with human edits are therefore preserved.
2. Keep `episodes.csv`, `audio/`, `repo_state.json`, `keyterms.py` in place (the Google repository is updated in
   place, not recreated).
3. Run Stages 0 → 7 in order, stopping at each gate.
4. Write `reports/run_<date>.md`: episodes processed, failures, total audio hours, estimated cost, Docs
   created/updated, Sheet row count.

---

## 6. Tests (`tests/`)

- `test_no_verbatim_absent`: grep all `.py` under `pipeline/` — the string `no_verbatim` appears only in comments.
- `test_json_utf8`: written JSON contains raw Vietnamese characters, no `\u1ea1`-style escapes.
- `test_spacing_kept`: word list with spacing tokens → reconstructed text equals the original string.
- `test_export_no_labels`: a tiny synthetic `.eaf` with two tiers → output has two paragraphs, no tier names.
- `test_export_verbatim`: annotation text with fillers and repetitions (`"thì thì là à ừ"`) survives export byte-for-byte.
- `test_eaf_not_overwritten`: `to_eaf` refuses to overwrite without `--force`.
- `test_sheet_rows`: row builder emits exactly the 10 columns above; no Guest/MC.
- `test_hyperlink_escape`: a title containing `"` produces a valid formula.

Google and ElevenLabs calls are mocked in tests; no network in `pytest`.

---

## 7. Definition of done

- [ ] All tests pass.
- [ ] Pilot report written; `gates/pilot_passed` created by a human.
- [ ] `episodes.csv` has ≈129 rows; every row has a JSON, an `.eaf` and a `.txt`; `failed.log` is empty.
- [ ] Cost log total ≈ $8.60 (abort threshold $12 never hit).
- [ ] Sheet has one row per episode, no Guest/MC columns; every title link opens the right Doc.
- [ ] Each Doc's text equals its `.txt` byte for byte; no speaker labels anywhere.
- [ ] A second `sync` run with no changes updates zero Docs.
- [ ] `run_all.py ingest` processes a new episode end to end with no manual steps besides ELAN verification.
- [ ] Old outputs preserved under `archive/`.

## 8. Still open (project lead, not Claude Code)

- Google account that owns the repository.
- Paragraph breaks at speaker change vs. pause-only.
- Keep `[cười]`-style audio event tags in delivered text or drop them.
- How overlapping speech is shown without labels (currently interleaved by start time).
- Written client decision on data residency (ElevenLabs US processing + Google Drive storage).
- Corpus orthography convention for fillers (standard vs. phonetic dialect spelling) — must be agreed before ELAN verification starts.
