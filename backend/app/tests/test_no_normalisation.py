"""The verbatim gate (PLAN §0.1, CLAUDE.md rule 1).

A hypothesis containing fillers, repetitions, a false start and a stutter must survive
**every** stage and **every** export byte-for-byte. If this file goes red, something in
the pipeline started "improving" the corpus and the linguistic data is being destroyed.

What counts as a failure here:

* a filler token missing from an export
* two adjacent identical words collapsed into one
* punctuation or capitalisation appearing where the engine emitted none
* whitespace "tidied"
* a diacritic escaped as ``\\u1ea1`` instead of written as UTF-8 (PLAN §13)

Encoding is not normalisation: XML escaping ``&`` in an EAF and CSV quoting a field are
reversible, and the tests check the *parsed* value, not the wire bytes.
"""

from __future__ import annotations

import csv as _csv
import io
import json
import re
import xml.etree.ElementTree as ET

import pytest

from app.exports import TIER_VERIFIED, csv, docx, eaf, json_verified, srt, txt
from app.pipeline import merge as merge_mod
from app.pipeline.asr import tokens_to_words
from app.pipeline.run import write_raw_json

MARK = "▁"

#: Fillers PLAN §4.2 measures recall on, plus a repetition, a false start and a stutter.
MESSY_WORDS = [
    "à", "à", "ừ", "thì", "là", "ờ", "ừm",
    "không", "cần", "phải", "quản", "nữa",
    "không", "cần", "phải", "quản", "nữa",
    "nh", "nhưng", "mà", "ấy", "nhé", "đấy",
]
MESSY_TEXT = " ".join(MESSY_WORDS)


def make_words(texts=MESSY_WORDS, step=0.2):
    return [
        {
            "i": i,
            "text": t,
            "start": round(i * step, 3),
            "end": round(i * step + 0.1, 3),
            "conf": -0.1,
        }
        for i, t in enumerate(texts)
    ]


def make_doc(texts=MESSY_WORDS):
    words = make_words(texts)
    utterances = merge_mod.build_utterances(words, max_gap_s=10.0)
    return {
        "schema_version": 2,
        "episode_id": "00000000-0000-0000-0000-000000000000",
        "source": {"filename": "ep042.mp3", "url": None, "sha256": "0" * 64},
        "audio": {"duration_s": len(texts) * 0.2, "sample_rate": 16000, "channels": 1},
        "engine": {"name": "zipformer-30m-rnnt-6000h", "params": {}},
        "vad": {"model": "silero_vad.onnx", "segments": [[0.0, len(texts) * 0.2]]},
        "words": words,
        "utterances": utterances,
        "created_at": "2026-09-22T09:00:00+07:00",
    }


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def test_tokens_to_words_keeps_every_filler_and_repetition():
    tokens = [f"{MARK}{w}" for w in MESSY_WORDS]
    times = [i * 0.2 for i in range(len(tokens))]
    words = tokens_to_words(tokens, times, [], 0.0, len(tokens) * 0.2)
    assert [w["text"] for w in words] == MESSY_WORDS


def test_grouping_keeps_every_filler_and_repetition():
    utterances = merge_mod.build_utterances(make_words())
    assert utterances[0]["text"] == MESSY_TEXT


def test_utterance_text_is_not_capitalised_or_punctuated():
    text = make_doc()["utterances"][0]["text"]
    assert text == text.lower() or text == MESSY_TEXT  # engine casing, ours added none
    assert not re.search(r"[.,!?;:]", text)
    assert text[0].islower()


# ---------------------------------------------------------------------------
# Exports — every one of them, every tier
# ---------------------------------------------------------------------------

def test_txt_export_is_unchanged():
    assert txt.render(make_doc()) == MESSY_TEXT + "\n"


def test_csv_export_round_trips_every_word_in_order():
    rows = list(_csv.DictReader(io.StringIO(csv.render(make_doc()))))
    assert [r["text"] for r in rows] == MESSY_WORDS


def test_srt_export_is_unchanged():
    body = srt.render(make_doc())
    cue_text = body.strip().split("\n")[2]
    assert cue_text == MESSY_TEXT


def test_eaf_annotation_values_are_unchanged():
    root = ET.fromstring(eaf.render(make_doc()))
    values = [el.text for el in root.iter("ANNOTATION_VALUE")]
    assert values == [MESSY_TEXT]


def test_eaf_xml_escaping_round_trips_rather_than_rewrites():
    """``&`` and ``<`` are escaped on the wire and come back identical."""
    doc = make_doc(["a&b", "x<y", "à"])
    root = ET.fromstring(eaf.render(doc))
    assert [el.text for el in root.iter("ANNOTATION_VALUE")] == ["a&b x<y à"]


def test_verified_json_keeps_the_asr_text_when_nothing_was_edited():
    out = json_verified.build(make_doc())
    u = out["utterances"][0]
    assert u["text_asr"] == MESSY_TEXT
    assert u["text"] == MESSY_TEXT
    assert u["text_verified"] is None


def test_verified_json_keeps_both_layers_when_a_human_edited():
    edited = MESSY_TEXT + " ạ"
    out = json_verified.build(make_doc(), overrides={0: {"text_verified": edited}})
    u = out["utterances"][0]
    assert u["text_asr"] == MESSY_TEXT   # the engine's original is never lost
    assert u["text"] == edited
    assert out["verification"]["utterances_verified"] == 1


def test_verified_tier_exports_use_the_human_text_verbatim():
    edited = "à à ừ thì  hai   khoảng trắng"   # deliberate double spaces
    doc = json_verified.build(make_doc(), overrides={0: {"text_verified": edited}})
    assert txt.render(doc, tier=TIER_VERIFIED) == edited + "\n"
    root = ET.fromstring(eaf.render(doc, tier=TIER_VERIFIED))
    assert [el.text for el in root.iter("ANNOTATION_VALUE")] == [edited]


def test_empty_verified_text_is_honoured_not_treated_as_absent():
    """A verifier blanking an utterance ("that was music") is a real edit."""
    doc = json_verified.build(make_doc(), overrides={0: {"text_verified": ""}})
    assert doc["utterances"][0]["text"] == ""
    assert txt.render(doc, tier=TIER_VERIFIED) == "\n"


# ---------------------------------------------------------------------------
# Encoding (PLAN §5, §13, CLAUDE.md rule 3)
# ---------------------------------------------------------------------------

DIACRITIC_TEXT = ["ạ", "ừm", "nghiệp", "vụ", "Huyền", "Đàn", "bà", "30+"]


def docx_document_xml(doc: dict) -> str:
    """The .docx is a zip; the verbatim checks apply to the XML part inside it."""
    import zipfile

    with zipfile.ZipFile(io.BytesIO(docx.render_bytes(doc))) as z:
        return z.read("word/document.xml").decode("utf-8")


@pytest.mark.parametrize(
    "render",
    [
        pytest.param(lambda d: txt.render(d), id="txt"),
        pytest.param(lambda d: csv.render(d), id="csv"),
        pytest.param(lambda d: srt.render(d), id="srt"),
        pytest.param(lambda d: eaf.render(d), id="eaf"),
        pytest.param(lambda d: json_verified.render(d), id="json_verified"),
        pytest.param(docx_document_xml, id="docx"),
    ],
)
def test_no_export_escapes_vietnamese_diacritics(render):
    body = render(make_doc(DIACRITIC_TEXT))
    assert "\\u1e" not in body and "\\u01b" not in body
    for token in DIACRITIC_TEXT:
        assert token in body


def test_raw_json_is_written_as_utf8_without_ascii_escapes(tmp_path):
    out = tmp_path / "ep.json"
    write_raw_json(make_doc(DIACRITIC_TEXT), out)
    body = out.read_text(encoding="utf-8")
    assert "\\u" not in body
    assert "ừm" in body and "nghiệp" in body
    reloaded = json.loads(body)
    assert [w["text"] for w in reloaded["words"]] == DIACRITIC_TEXT


def test_raw_json_refuses_to_overwrite_itself(tmp_path):
    """PLAN §0.2: the raw JSON is written once and never edited."""
    out = tmp_path / "ep.json"
    write_raw_json(make_doc(), out)
    with pytest.raises(FileExistsError):
        write_raw_json(make_doc(), out)


# ---------------------------------------------------------------------------
# Whole-pipeline guard
# ---------------------------------------------------------------------------

def test_word_count_is_identical_across_every_export():
    """Nothing anywhere drops or merges a token."""
    doc = make_doc()
    expected = len(MESSY_WORDS)

    txt_words = txt.render(doc).rstrip("\n").split(" ")
    csv_rows = list(_csv.DictReader(io.StringIO(csv.render(doc))))
    srt_words = srt.render(doc).strip().split("\n")[2].split(" ")
    eaf_words = ET.fromstring(eaf.render(doc)).find(".//ANNOTATION_VALUE").text.split(" ")
    verified_words = json_verified.build(doc)["utterances"][0]["text"].split(" ")

    # The docx body paragraph carrying the utterance (the first one is the title).
    docx_xml = ET.fromstring(docx_document_xml(doc))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    docx_texts = [t.text or "" for t in docx_xml.iter(f"{w}t")]
    docx_words = docx_texts[-1].split(" ")

    assert len(txt_words) == expected
    assert len(docx_words) == expected
    assert len(csv_rows) == expected
    assert len(srt_words) == expected
    assert len(eaf_words) == expected
    assert len(verified_words) == expected


def test_a_source_module_never_calls_a_text_cleaning_helper():
    """A cheap tripwire against the reflex to 'just tidy this up'.

    Catches the obvious offenders being applied to transcript text anywhere under
    ``app/pipeline`` and ``app/exports``.
    """
    from pathlib import Path

    banned = re.compile(
        r"\.(capitalize|title|casefold)\(\)"
        r"|\bre\.sub\(\s*r?['\"][^'\"]*\\s"
        r"|\bunicodedata\.normalize\b"
    )
    roots = [Path(__file__).resolve().parents[1] / d for d in ("pipeline", "exports")]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if banned.search(line):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "text-cleaning call in the pipeline:\n" + "\n".join(offenders)


def test_no_export_carries_speaker_information():
    """An old raw JSON (schema 1) still has speaker clusters; no export may show them."""
    doc = make_doc()
    for w in doc["words"]:
        w["speaker"] = 3
    for u in doc["utterances"]:
        u["speaker"] = 3
    doc["diarization"] = {"segments": [{"start": 0.0, "end": 9.0, "speaker": 3}]}

    assert "SPEAKER" not in txt.render(doc) + srt.render(doc) + eaf.render(doc)
    assert "speaker" not in csv.render(doc).splitlines()[0]
    assert "speaker" not in json_verified.render(doc)
    assert "SPEAKER" not in docx_document_xml(doc)
