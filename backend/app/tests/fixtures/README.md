# Test fixtures

`sample_raw.json` — a small PLAN §5 raw JSON document, hand-built, deliberately messy:
fillers (`à ừ thì là ờ ạ`), a verbatim repetition (`không cần phải quản nữa` twice) and
two speaker clusters. Use it via the `raw_doc` fixture in `conftest.py`.

Do not "tidy" it. Its messiness is the point — see PLAN §0.1 and
`test_no_normalisation.py`.

Audio fixtures are **not** committed: episode audio is client material and vox-pop voices
are identifiable private individuals (PLAN §0.3). Pilot clips live in `pilot/`, which is
gitignored.
