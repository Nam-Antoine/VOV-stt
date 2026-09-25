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
