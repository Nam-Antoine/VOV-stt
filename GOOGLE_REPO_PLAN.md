# VOV-stt — Google Sheet + Docs repository: implementation plan for Claude Code

Version 1.0 · 25 Sep 2026 · Detailed breakdown of `PHASE4_PLAN.md` Part B (plus the one piece of Part A it depends on).
Precedence: `CLAUDE.md` > `PLAN.md` > `PHASE4_PLAN.md` > this file.

---

## How to use this file

Put it in the repo root next to `PHASE4_PLAN.md`, then paste this into Claude Code:

> Read `CLAUDE.md`, `PLAN.md`, `PHASE4_PLAN.md` and `GOOGLE_REPO_PLAN.md`, in that order. Implement
> `GOOGLE_REPO_PLAN.md` task by task on a branch `t6-google-repo`. After each task, run `ruff`, `pytest` and the
> verbatim gate, show me the diff summary, and continue only if everything is green. Stop at every **CHECKPOINT** and
> wait for me. Don't decide anything listed under "Owner decisions". Start by giving me a short outline of how the
> existing export, readable-layer and job code works, and where each task will hook in.

---

## 0. What gets built

- The script creates, inside the owner's Google Drive:
  - a folder `Đàn bà 30+ Corpus`,
  - a Sheet `Đàn bà 30+ Corpus — Index` in that folder, one row per episode,
  - one Google Doc per transcribed episode in that folder, with no speaker labels.
- The Sheet's Title cell links to the episode's Doc. **No Guest column, no MC column.**
- Docs and Sheet are generated from the database. They are never read back and never edited by hand.
- The feature is **off by default** (`GOOGLE_REPO_ENABLED=false`) until the owner finishes the auth handoff.

## 1. Rules

1. No change to transcript words. The Doc body is produced by the same text path as the other exports, with labels
   turned off. The verbatim gate must cover it.
2. OAuth desktop client, scope `https://www.googleapis.com/auth/drive.file` **only**. No service account. No broader
   Drive scope.
3. Secrets (`credentials.json`, `token.json`) live in the data volume, never in git (the repo is public), never in
   logs, never in API responses.
4. Nothing is ever deleted in Google Drive by code. Orphaned Docs are reported, not removed.
5. Migrations are additive only.
6. Every Google call in tests is mocked. No network during `pytest`.
7. One worker, existing thread/nice settings. Google sync must not slow ASR noticeably.

---

## 2. Tasks

### Task 1 — Shared no-label text renderer (Part A dependency)

- Find where `.docx`/`.txt` exports build their text. Extract or add one function, e.g.
  `render_plain(episode, layer: Literal["readable","verbatim"], labels: bool) -> str`.
- `labels=False`: no speaker names or `Name:` prefixes. New paragraph on speaker change, or on a pause > 1.5 s when
  diarization data is absent. Paragraphs separated by one blank line; file ends with `\n`.
- If `layer="readable"` isn't available (punctuation model missing, or speakers pending), return the verbatim layer
  and tell the caller which layer was used.
- Tests:
  - `test_render_no_labels`: a two-speaker fixture produces no speaker names.
  - Extend `test_no_normalisation`: the words of `render_plain(..., labels=False)` equal the verbatim layer's words,
    token for token, for both layers (ignoring case and punctuation for `readable`).

### Task 2 — Config and dependencies

- Add to `backend/pyproject.toml`: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`,
  `google-auth-httplib2`. (These are not LLM clients, so CLAUDE.md rule 7 is not affected.)
- New settings with defaults:

| Env var | Default |
|---|---|
| `GOOGLE_REPO_ENABLED` | `false` |
| `GOOGLE_CREDENTIALS_PATH` | `/data/google/credentials.json` |
| `GOOGLE_TOKEN_PATH` | `/data/google/token.json` |
| `GOOGLE_DOC_LAYER` | `readable` |
| `GOOGLE_FOLDER_NAME` | `Đàn bà 30+ Corpus` |
| `GOOGLE_SHEET_NAME` | `Đàn bà 30+ Corpus — Index` |
| `GOOGLE_EDIT_DEBOUNCE_MIN` | `10` |

- Add them to `.env.example` with comments. Add `/data/google/` and `credentials.json` / `token.json` patterns to
  `.gitignore`. Make sure `docker-compose.yml` mounts the data volume path in the worker and api containers.

### Task 3 — Migration (additive)

- `google_repo_state`: `key TEXT PK`, `value TEXT`, `updated_at` (stores `folder_id`, `sheet_id`).
- `episode_google_doc`: `episode_id FK UNIQUE`, `doc_id`, `text_sha256`, `layer_used`, `doc_title`, `synced_at`,
  `last_error NULL`.
- Test upgrade → downgrade → upgrade in the existing CI migrations job. The downgrade drops **only** these two tables.

### Task 4 — `app/google_repo/auth.py`

- `--init` mode for the owner's **laptop**. It must run with only `google-auth-oauthlib` installed: no DB, no app
  settings import, no Docker.

```
python -m app.google_repo.auth --init --credentials ./credentials.json --out ./token.json
```

  It runs `InstalledAppFlow.from_client_secrets_file(...).run_local_server(port=0)` with the `drive.file` scope and
  writes `token.json`. Print where the file went and the next step (copy it to the VPS).
- Runtime `get_credentials()` for the VPS: load the token, refresh if expired, and write back atomically (temp file +
  rename) if the refresh token changed.
  - `invalid_grant` or a missing/revoked token raises `GoogleAuthError` with a plain-language message
    ("re-run auth --init on your laptop"). It is never retried in a loop.
- `--check` mode prints the owning account's email (`drive.about.get(fields="user")`) and the token expiry, without
  printing any secret.

### Task 5 — `app/google_repo/docs.py`

- `ensure_folder()`: create the folder once; store its ID in `google_repo_state`.
- `upsert_doc(episode)`:
  - Text = `render_plain(episode, settings.GOOGLE_DOC_LAYER, labels=False)`. Compute its SHA-256.
  - If there's no Doc: `documents.create(title)`, then move it into the folder (`files.update addParents`, remove
    existing parents), then `insertText` at index 1.
  - If the Doc exists and the hash changed: `documents.get` → `deleteContentRange` from 1 to `endIndex-1` (only if
    `endIndex > 2`) → `insertText`.
  - If the Doc exists and the title changed: rename via `files.update(name=...)`.
  - If nothing changed: no API call.
  - Doc title: `<episode code> — <title>`.
  - Store `doc_id`, the hash, `layer_used`, `synced_at`; clear `last_error`.
- Rate limiting: at most 1 Doc write per 1.1 s (Docs API limit is 60 writes/min per user). Retry 429/5xx with
  exponential backoff (max 5 tries). On final failure, store `last_error` and continue with the next episode.
- A Doc that returns 404 (deleted by someone in Drive): clear the stored ID and recreate it on the next sync. Log it.

### Task 6 — `app/google_repo/sheet.py`

- `ensure_sheet()`: create it once inside the folder, freeze the header row, store its ID.
- `rebuild_sheet()`: build every row from the DB, then `values.clear("A:Z")` + `values.update("A1", USER_ENTERED)`.
- Columns, exactly and in this order:

| Episode ID | Title | Air date | Duration | Source URL | Tier | Status | Verified by | Verified date | Syllables |
|---|---|---|---|---|---|---|---|---|---|

  - Title: `=HYPERLINK("<https://docs.google.com/document/d/ID/edit>", "<title>")`, with `"` in the title escaped
    as `""`. Plain title if there's no Doc yet.
  - Duration: prefix with `'` so Sheets keeps `15:00` as text.
  - Syllables: `len(text.split())` of the Doc text; empty if there's no Doc.
  - Sorted by air date, oldest first.
- Test `test_sheet_header_exact`: the header equals the list above. Assert that `Guest` and `MC` are absent in any
  casing.

### Task 7 — `app/google_repo/sync.py` and jobs

- CLI:
  - `python -m app.google_repo.sync --all` upserts every Doc, then rebuilds the Sheet.
  - `--episode <id>` upserts one Doc, then rebuilds the Sheet.
  - `--status` prints counts: synced / pending / errors / orphans. It makes no writes.
- Worker job type `google_sync` (payload: episode ID or `all`):
  - Enqueued when an ASR job finishes.
  - Enqueued after a verification edit is saved, debounced by `GOOGLE_EDIT_DEBOUNCE_MIN` (one pending sync per
    episode at most).
  - Every entry point returns immediately when `GOOGLE_REPO_ENABLED=false`.
- Orphans are Docs in `episode_google_doc` whose episode no longer exists. Report them in `--status`; never delete.
- Makefile targets: `google-sync` (`--all`), `google-status`, `google-check` (`auth --check`).

### Task 8 — Health and UI

- `/api/health` gains `google_repo`, with one of these values:
  - `disabled`
  - `ok` (token loads and refreshes)
  - `token_invalid`
  - `error: <short reason>`

  It never includes secrets.
- The Exports page shows a "Google Sheet" link (the Sheet URL) when enabled, plus the last full sync time. It is
  read-only; there is no auth UI in the web app.

### Task 9 — Tests (all mocked)

- A fake Google service object records calls. Cover:
  - first sync creates folder + sheet + docs;
  - a second identical sync makes **zero** write calls;
  - a text change rewrites one Doc;
  - a title change renames it;
  - a 404 leads to recreation;
  - a 429 is retried, then succeeds;
  - `invalid_grant` gives a clear error and no retry loop;
  - disabled means no calls at all.
- `test_no_secrets_logged`: capture logs during a sync; assert that the token and client secret strings never appear.

### Task 10 — README

Add a "Google repository" section with the owner's steps:

1. In Google Cloud, enable the Sheets, Docs and Drive APIs.
2. Create an OAuth client ID of type **Desktop app**, and download the JSON **right away** (the secret is shown only
   once). Set the Audience to **In production**, because testing-mode tokens expire after 7 days.
3. On a laptop, run `auth --init` with the owning Google account → you get `token.json`.
4. Copy `credentials.json` and `token.json` to `/data/google/` on the VPS.
5. Set `GOOGLE_REPO_ENABLED=true`, restart, then run `make google-check` and `make google-sync`.
6. In Drive, share the folder with the client as **Viewer**.
7. Rule: edit transcripts and metadata in the app, never in the Sheet or Docs — every sync overwrites them.

**CHECKPOINT A:** all tasks merged on the branch, CI green. Stop. Give the owner the exact commands for steps 3–4
(with the real container path), then wait for them to confirm `token.json` is in place.

### Task 11 — First live sync (after the owner's confirmation)

1. Run `make google-check` and show the owning account's email. **CHECKPOINT B:** the owner confirms it's the right
   account.
2. Run `python -m app.google_repo.sync --episode <pilot episode>` for one episode only. Report the Sheet URL and Doc
   URL. **CHECKPOINT C:** the owner opens both and confirms: no labels, text correct, link works, no Guest/MC.
3. Run `make google-sync`. Report counts, errors and elapsed time.
4. Run `make google-sync` again and confirm zero Doc writes.

---

## 3. Definition of done

- [ ] CI green, including the verbatim gate, migrations job and new tests.
- [ ] One folder, one Sheet, one Doc per transcribed episode in the owner's Drive.
- [ ] Sheet header is exactly the 10 columns above; no Guest/MC.
- [ ] Every title link opens the right Doc; Docs have no speaker labels; words match the verbatim layer.
- [ ] A repeat sync writes nothing; an edit in the app shows up in the Doc within the debounce window.
- [ ] `/api/health` shows `google_repo: ok`; no secrets in logs or git.
- [ ] README section complete.

## 4. Owner decisions (Claude Code asks, never decides)

- Which Google account owns the repository.
- `GOOGLE_DOC_LAYER`: `readable` (punctuated, sentence case) or `verbatim` (upper-case, no punctuation).
- Whether a Sheet link on the Exports page is wanted, or it stays private to the owner.
- Data-residency sign-off for storing transcripts in Google Drive.
