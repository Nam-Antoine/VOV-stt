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
9. No diarization and no speaker labels anywhere (removed 25 Sep 2026). Don't add them back,
   and never build speaker identification of real people.
10. Do not start T3+ until pilot/RESULTS.md shows the verbatim gate passed and is signed off.

Commands: `make dev`, `make test`, `make pilot`, `make deploy`, `make export EP=<slug>`.
11. Projects: every episode belongs to a project (`episodes.project_id`). Each project has its
    own Drive folder ("<name> Corpus") and index Sheet ("<name> Corpus — Index"). Code never
    deletes anything in Google Drive. Editors to share new folders with come from
    `GOOGLE_SHARE_EDITORS` in `.env` — never write e-mail addresses into the repo.

## Working rules (for Claude)

- Multi-step request: write a checklist first and finish every item on it.
- Ask the owner only when a decision genuinely cannot be made from the request, the code or
  a sensible default, or when a test fails and the fix is not obvious.
- Keep going until the checklist is done. Stop only when stuck, or before deleting anything
  important (data, audio, raw JSON, Drive files, DB rows carrying human edits) — ask first.
- End with a report: what was done, what was verified, what is still a concern.
- After finishing a feature, sweep what was just added for dead code, duplicate logic,
  unused components, and unnecessary complexity, and clean it up before reporting done.
