"""Plain text for the Google Docs (GOOGLE_REPO_PLAN Task 1): no labels, sane layout."""

from __future__ import annotations

import pytest

from app.exports import plain


def items_with_speakers():
    """What an old two-speaker transcript looks like: speaker fields on every item."""
    return [
        {"start": 0.0, "end": 2.0, "text": "chào các bạn", "speaker": 0,
         "speaker_label": "Host"},
        {"start": 2.2, "end": 4.0, "text": "chào chị", "speaker": 1,
         "speaker_label": "Guest"},
        {"start": 6.0, "end": 8.0, "text": "hôm nay mình nói về tuổi ba mươi",
         "speaker": 0, "speaker_label": "Host"},
    ]


@pytest.mark.parametrize("layer", ["readable", "verbatim"])
def test_render_no_labels(layer):
    body = plain.render(items_with_speakers(), layer=layer, labels=False)
    for mark in ("Host", "Guest", "MC", "Khách", "SPEAKER", "Speaker", "Người nói"):
        assert mark not in body
    assert not any(line.rstrip().endswith(":") for line in body.splitlines())


def test_labels_cannot_be_turned_on():
    with pytest.raises(ValueError):
        plain.render(items_with_speakers(), layer="verbatim", labels=True)


def test_unknown_layer_is_refused():
    with pytest.raises(ValueError):
        plain.render(items_with_speakers(), layer="shouting", labels=False)


def test_pause_over_1_5_s_starts_a_paragraph():
    body = plain.render(items_with_speakers(), layer="verbatim")
    assert body == "chào các bạn chào chị\n\nhôm nay mình nói về tuổi ba mươi\n"


def test_long_passage_is_cut_at_an_utterance_end():
    items = [{"start": k * 1.0, "end": k * 1.0 + 0.9, "text": " ".join(["từ"] * 30)}
             for k in range(6)]
    paras = plain.render(items, layer="verbatim").rstrip("\n").split("\n\n")
    assert [len(p.split()) for p in paras] == [90, 90]


def test_empty_transcript_is_one_newline():
    assert plain.render([], layer="verbatim") == "\n"
