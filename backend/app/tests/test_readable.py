"""The readable layer adds punctuation and case — and nothing else.

No model is loaded here: a scripted ``_predict`` stands in for ViBERT-capu so the tests
pin *our* contract (which actions are accepted, the verbatim check, staleness), not the
model's judgement. The real model is exercised in the deploy check, not in CI.
"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from app import readable as readable_mod
from app.exports import readable as readable_export
from app.exports import txt
from app.pipeline import punctuate

MESSY = "à à ừ thì là ờ ừm không cần phải quản nữa không cần phải quản nữa nh nhưng mà ấy"


def scripted(actions_for):
    """A Punctuator whose model returns ``actions_for(tokens)``."""
    p = punctuate.Punctuator(params=punctuate.PunctParams())
    p._predict = actions_for  # type: ignore[method-assign]
    return p


def keep(tokens):
    return ["$KEEP"] * len(tokens)


def test_only_marks_and_case_are_applied():
    def actions(tokens):
        out = keep(tokens)
        out[0] = "$TRANSFORM_CASE_CAPITAL"
        out[2] = "$APPEND_,"
        out[-1] = "$APPEND_."
        return out

    got = scripted(actions).restore("vâng thì là".split())
    assert got == ["Vâng", "thì", "là."]


def test_merge_and_verb_actions_are_refused():
    """$MERGE_SPACE would join two words; verb transforms would rewrite one."""
    def actions(tokens):
        return ["$MERGE_SPACE", "$TRANSFORM_VERB_VB_VBN", "@@UNKNOWN@@"][: len(tokens)]

    words = "không cần phải".split()
    assert scripted(actions).restore(words) == words


def test_every_filler_and_repetition_survives():
    def actions(tokens):
        return ["$APPEND_," if k % 3 == 0 else "$TRANSFORM_CASE_CAPITAL"
                for k in range(len(tokens))]

    words = MESSY.split()
    got = scripted(actions).restore(words)
    assert len(got) == len(words)
    assert [punctuate.strip_marks(w).lower() for w in got] == words


def test_a_word_never_gets_two_marks():
    got = scripted(lambda t: ["$APPEND_."] * len(t)).restore(["vâng."])
    assert got == ["vâng."]


def test_long_turns_are_chunked_without_losing_words():
    words = MESSY.split() * 10  # > 48-word chunks, with overlap
    got = scripted(lambda t: ["$APPEND_,"] * len(t)).restore(words)
    assert punctuate.same_words(words, got)


def test_same_words_rejects_any_word_change():
    assert punctuate.same_words(["thì", "là"], ["Thì,", "là."])
    assert not punctuate.same_words(["thì", "là"], ["Thì"])
    assert not punctuate.same_words(["thì", "thì"], ["thì"])
    assert not punctuate.same_words(["ờ"], ["ừ"])


def test_turn_is_cut_back_into_its_utterances():
    p = scripted(lambda t: ["$KEEP"] * (len(t) - 1) + ["$APPEND_."])
    out = punctuate.readable_turn(p, ["xin chào", "mọi người"])
    assert out == ["Xin chào", "mọi người."]


def test_verifier_typed_capitals_survive_but_engine_capitals_do_not():
    p = scripted(lambda t: ["$KEEP"] * (len(t) - 1) + ["$APPEND_."])
    typed, engine = "tới Hà Nội nghe VOV2", "TỚI HÀ NỘI"
    assert punctuate.readable_turn(p, [typed]) == ["Tới Hà Nội nghe VOV2."]
    assert punctuate.readable_turn(p, [engine]) == ["Tới hà nội."]


def test_sentences_split_at_full_stops_and_questions():
    assert punctuate.sentences("Xin chào. Vì sao vậy? Thế thôi") == [
        "Xin chào.", "Vì sao vậy?", "Thế thôi"]


# --- staleness ---------------------------------------------------------------

def utt(i, start, text_asr, *, verified=None, readable=None, source=None):
    return SimpleNamespace(i=i, start_s=float(start), end_s=float(start) + 1.0,
                           text_asr=text_asr,
                           text_verified=verified, text_readable=readable,
                           readable_from=source)


def test_refresh_recomputes_only_stale_passages(monkeypatch):
    rows = [
        utt(0, 0.0, "xin chào", readable="Xin chào.", source="xin chào"),
        # 3 s of silence after utterance 0: a new passage.
        utt(1, 4.0, "vâng ạ", verified="vâng ạ ạ", readable="Vâng ạ.", source="vâng ạ"),
        utt(2, 5.2, "thế thì"),
    ]
    monkeypatch.setattr(readable_mod, "ordered_utterances", lambda s, t: rows)
    session = SimpleNamespace(flush=lambda: None)
    p = scripted(lambda t: ["$KEEP"] * (len(t) - 1) + ["$APPEND_."])

    written = readable_mod.refresh(session, "t", p)

    assert written == 2                       # the edited passage (1, 2); 0 untouched
    assert rows[0].text_readable == "Xin chào."
    assert rows[1].readable_from == "vâng ạ ạ"   # computed from the human's text
    assert rows[1].text_verified == "vâng ạ ạ"   # corpus layer untouched
    assert rows[1].text_asr == "vâng ạ"
    assert rows[2].text_readable == "thế thì."
    assert not any(readable_mod.is_stale(u) for u in rows)


# --- exports -------------------------------------------------------------------

ITEMS = [
    {"start": 0.0, "end": 2.0, "text": "Kính chào quý vị. Hôm nay"},
    {"start": 2.4, "end": 5.0, "text": "chúng ta nói về tuổi ba mươi."},
    # 2 s of silence: a new paragraph.
    {"start": 7.0, "end": 8.0, "text": "Xin chào. Vâng?"},
]


def test_readable_txt_has_one_paragraph_per_passage_and_no_labels():
    out = readable_export.render_txt(ITEMS, title="ĐÀN BÀ 30+")
    assert out == (
        "ĐÀN BÀ 30+\n\n"
        "Kính chào quý vị. Hôm nay chúng ta nói về tuổi ba mươi.\n\n"
        "Xin chào. Vâng?\n"
    )


def test_readable_docx_has_one_paragraph_per_passage():
    data = readable_export.render_docx(ITEMS, title="T")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert xml.count("<w:p>") == 3  # title + 2 passages
    assert "Kính chào quý vị. Hôm nay chúng ta nói về tuổi ba mươi." in xml
    assert "\\u1e" not in xml


def test_corpus_txt_export_ignores_the_readable_layer():
    doc = {"utterances": [{"i": 0, "start": 0.0, "end": 1.0,
                            "text": MESSY, "text_readable": "À, à. Ừ thì là…"}]}
    assert txt.render(doc) == MESSY + "\n"


@pytest.mark.parametrize("fmt", ["readable.txt", "readable.docx", "readable.pdf"])
def test_readable_formats_are_registered(fmt):
    from app.api.exports import FORMATS
    assert fmt in FORMATS


# --- decoding: ensemble mean, biases, refused actions ------------------------------

LABELS = ["$KEEP", "$TRANSFORM_CASE_CAPITAL", "$APPEND_,", "$APPEND_.", "$MERGE_SPACE"]


class FakeHead:
    def __init__(self, rows, weight=1.0):
        import numpy as np
        self.rows = np.array(rows, dtype=float)
        self.spec = SimpleNamespace(weight=weight)
        self.labels = LABELS

    def probs(self, tokens):
        return self.rows


def decoder(heads, **params):
    return punctuate.Punctuator(params=punctuate.PunctParams(**params), _heads=heads,
                                _labels=LABELS)


START = [1, 0, 0, 0, 0]


def test_a_refused_action_never_wins_even_when_most_likely():
    p = decoder([FakeHead([START, [0.1, 0.0, 0.3, 0.0, 0.6]])])
    assert p._predict(["x"]) == ["$APPEND_,"]


def test_stop_bias_turns_a_close_comma_into_a_full_stop():
    row = [0.1, 0.0, 0.5, 0.4, 0.0]
    assert decoder([FakeHead([START, row])])._predict(["x"]) == ["$APPEND_,"]
    assert decoder([FakeHead([START, row])], stop_bias=1.0)._predict(["x"]) == ["$APPEND_."]


def test_keep_bias_lets_a_close_edit_win():
    row = [0.5, 0.4, 0.1, 0.0, 0.0]
    assert decoder([FakeHead([START, row])])._predict(["x"]) == ["$KEEP"]
    assert decoder([FakeHead([START, row])], keep_bias=0.5)._predict(["x"]) == [
        "$TRANSFORM_CASE_CAPITAL"]


def test_ensemble_averages_by_weight():
    a = FakeHead([START, [0.0, 0.0, 1.0, 0.0, 0.0]], weight=1.0)
    b = FakeHead([START, [0.0, 0.0, 0.0, 1.0, 0.0]], weight=3.0)
    assert decoder([a, b])._predict(["x"]) == ["$APPEND_."]


def test_a_word_after_a_stop_is_capitalised_even_from_the_last_pass():
    # Every pass puts a stop after the first word only; nothing ever capitalises.
    p = scripted(lambda t: ["$APPEND_."] + ["$KEEP"] * (len(t) - 1))
    assert p.restore(["lão", "chồng", "vừa", "mua"]) == ["lão.", "Chồng", "vừa", "mua"]



def test_readable_pdf_renders_vietnamese():
    import os
    if not os.path.exists(f"{readable_export.PDF_FONT_DIR}/DejaVuSerif.ttf"):
        pytest.skip("DejaVu fonts not installed")
    pytest.importorskip("fpdf")
    out = readable_export.render_pdf(ITEMS, title="ĐÀN BÀ 30+")
    assert out.startswith(b"%PDF-") and out.rstrip().endswith(b"%%EOF")
    assert b"DejaVuSerif" in out  # the Vietnamese-capable font is embedded


def test_download_all_route_accepts_only_reading_formats(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.db import get_session
    from app.main import app

    monkeypatch.setattr(type(settings), "punct_available", lambda self: True)

    class NoEpisodes:
        def scalars(self, _):
            return []

    app.dependency_overrides[get_session] = lambda: NoEpisodes()
    try:
        client = TestClient(app)
        for fmt in ("readable.docx", "readable.pdf", "readable.txt"):
            r = client.get(f"/api/exports/all.zip?fmt={fmt}")
            assert r.status_code == 200 and r.content[:2] == b"PK", fmt
        assert client.get("/api/exports/all.zip?fmt=json").status_code == 422
        # No model: one clear 503, not a zip of per-episode failures.
        monkeypatch.setattr(type(settings), "punct_available", lambda self: False)
        assert client.get("/api/exports/all.zip").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_download_is_named_after_the_episode_title():
    from urllib.parse import unquote

    from app.api.exports import attachment, file_stem

    ep = SimpleNamespace(title='Phụ  nữ: "khí chất"?', slug="20211102-f29599")
    assert file_stem(ep) == "Phụ nữ khí chất"
    header = attachment(ep, "docx")
    assert 'filename="20211102-f29599.docx"' in header
    assert unquote(header.split("UTF-8''")[1]) == "Phụ nữ khí chất.docx"
    assert file_stem(SimpleNamespace(title="", slug="ep1")) == "ep1"


def test_long_passage_is_cut_at_a_sentence_end_after_80_words():
    sentence = " ".join(["một"] * 29) + " hai."   # 30 words
    items = [{"start": float(k), "end": float(k) + 0.9, "text": sentence} for k in range(4)]
    paras = readable_export.blocks(items)
    # 30 + 30 + 30 = 90 >= 80 closes the first paragraph; the fourth sentence is left.
    assert [len(p.split()) for p in paras] == [90, 30]
    assert all(p.endswith(".") for p in paras)
    assert " ".join(paras) == " ".join(it["text"] for it in items)   # nothing lost


def test_corpus_docx_has_one_paragraph_per_utterance_and_no_headings():
    from app.exports import docx

    doc = {"utterances": [
        {"i": 0, "start": 0.0, "end": 1.0, "text": "à thì"},
        {"i": 1, "start": 1.2, "end": 2.0, "text": "ừ ừ"},
    ]}
    xml = zipfile.ZipFile(io.BytesIO(docx.render_bytes(doc, title="T"))).read(
        "word/document.xml").decode("utf-8")
    assert xml.count("<w:p>") == 3 and "à thì" in xml and "ừ ừ" in xml
    assert "Speaker" not in xml
