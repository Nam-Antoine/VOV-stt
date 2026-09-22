"""Token → word roll-up (PLAN §2.2).

The roll-up is where "words glued together / spacing wrong" (PLAN §13) comes from, and
where a filler could silently disappear into its neighbour. These tests pin the marker
handling, the timestamp arithmetic and the confidence averaging.
"""

from __future__ import annotations

import pytest

from app.pipeline.asr import is_word_start, strip_marker, tokens_to_words

MARK = "▁"  # ▁


class TestMarkers:
    """sherpa-onnx 1.13.8 emits ' RỒI'; other exports emit '▁RỒI'. Both are word starts."""

    @pytest.mark.parametrize("token", [f"{MARK}kính", " kính"])
    def test_marked_tokens_start_words(self, token):
        assert is_word_start(token)
        assert strip_marker(token) == "kính"

    @pytest.mark.parametrize("token", ["ính", "Ạ", ""])
    def test_bare_tokens_continue_words(self, token):
        assert not is_word_start(token)
        assert strip_marker(token) == token


def test_splits_on_marker_not_on_spaces():
    """Each ▁-group is one word; continuation pieces glue onto the word before."""
    words = tokens_to_words(
        [f"{MARK}G", "Ạ", "O", f"{MARK}CHO", f"{MARK}NÀY"],
        [0.0, 0.1, 0.2, 0.5, 0.8],
        [],
        offset_s=0.0,
        seg_end_s=1.0,
    )
    assert [w["text"] for w in words] == ["GẠO", "CHO", "NÀY"]


def test_space_marker_from_sherpa_onnx_1_13():
    """The exact token shape the installed runtime returns (see asr.py docstring)."""
    words = tokens_to_words(
        [" RỒI", " CŨNG", " G", "Ạ", "O"],
        [0.0, 0.16, 0.48, 0.60, 0.70],
        [-0.1, -0.2, -0.3, -0.4, -0.5],
        offset_s=0.0,
        seg_end_s=1.0,
    )
    assert [w["text"] for w in words] == ["RỒI", "CŨNG", "GẠO"]


def test_timestamps_are_absolute_and_chained():
    """start = offset + token time; end = the next word's start (PLAN §2.2)."""
    words = tokens_to_words(
        [f"{MARK}kính", f"{MARK}chào", f"{MARK}quý"],
        [0.0, 0.2, 0.5],
        [],
        offset_s=10.0,
        seg_end_s=0.9,
    )
    assert [w["start"] for w in words] == [10.0, 10.2, 10.5]
    assert [w["end"] for w in words] == [10.2, 10.5, 10.9]


def test_last_word_ends_at_segment_end():
    words = tokens_to_words([f"{MARK}a"], [0.3], [], offset_s=5.0, seg_end_s=2.0)
    assert words[0]["end"] == pytest.approx(7.0)


def test_conf_is_mean_logprob_over_the_words_tokens():
    words = tokens_to_words(
        [f"{MARK}G", "Ạ", "O", f"{MARK}CHO"],
        [0.0, 0.1, 0.2, 0.5],
        [-0.3, -0.6, -0.9, -0.1],
        offset_s=0.0,
        seg_end_s=1.0,
    )
    assert words[0]["conf"] == pytest.approx(-0.6)   # mean of -0.3, -0.6, -0.9
    assert words[1]["conf"] == pytest.approx(-0.1)


def test_conf_is_none_when_the_runtime_gives_no_logprobs():
    """PLAN §2: ys_log_probs is only present in some builds — omit, never invent."""
    words = tokens_to_words([f"{MARK}a", f"{MARK}b"], [0.0, 0.1], [], 0.0, 0.5)
    assert all(w["conf"] is None for w in words)


def test_short_logprob_list_does_not_crash_or_shift():
    words = tokens_to_words(
        [f"{MARK}a", f"{MARK}b", f"{MARK}c"], [0.0, 0.1, 0.2], [-0.5], 0.0, 0.5
    )
    assert words[0]["conf"] == pytest.approx(-0.5)
    assert words[1]["conf"] is None and words[2]["conf"] is None


def test_leading_unmarked_token_still_opens_a_word():
    """A segment that begins mid-word must not be dropped (PLAN §2.2's `or cur is None`)."""
    words = tokens_to_words(["ính", f"{MARK}chào"], [0.0, 0.3], [], 0.0, 0.5)
    assert [w["text"] for w in words] == ["ính", "chào"]


def test_empty_input_gives_no_words():
    assert tokens_to_words([], [], [], 0.0, 1.0) == []


def test_repeated_fillers_are_three_separate_words():
    """CLAUDE.md rule 1: no dedupe, not even of identical adjacent tokens."""
    words = tokens_to_words(
        [f"{MARK}à", f"{MARK}à", f"{MARK}ừ", f"{MARK}thì"],
        [0.0, 0.2, 0.4, 0.6],
        [],
        0.0,
        0.8,
    )
    assert [w["text"] for w in words] == ["à", "à", "ừ", "thì"]


def test_diacritics_survive_the_roll_up():
    tokens = [f"{MARK}nghiệp", f"{MARK}vụ", f"{MARK}ạ"]
    words = tokens_to_words(tokens, [0.0, 0.2, 0.4], [], 0.0, 0.6)
    assert [w["text"] for w in words] == ["nghiệp", "vụ", "ạ"]
