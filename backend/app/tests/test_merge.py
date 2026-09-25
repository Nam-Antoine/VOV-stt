"""Utterance and passage grouping (PLAN §3).

Grouping is the last stage before the immutable raw JSON, so a word lost here is lost
for good. These tests pin that grouping follows pauses only and never drops, reorders
or rewrites a word.
"""

from __future__ import annotations

import pytest

from app.pipeline.merge import build_utterances, passages


def word(i, text, start, end):
    return {"i": i, "text": text, "start": start, "end": end, "conf": None}


def utt(start, end):
    return {"start": start, "end": end}


class TestBuildUtterances:
    def test_gap_over_the_threshold_starts_a_new_utterance(self):
        words = [
            word(0, "một", 0.0, 0.3),
            word(1, "hai", 1.0, 1.3),   # 0.7 s gap > 0.5 s
        ]
        assert [u["text"] for u in build_utterances(words)] == ["một", "hai"]

    def test_gap_at_the_threshold_stays_in_one_utterance(self):
        words = [
            word(0, "một", 0.0, 0.3),
            word(1, "hai", 0.8, 1.1),   # exactly 0.5 s
        ]
        assert len(build_utterances(words)) == 1

    def test_max_gap_is_configurable(self):
        words = [
            word(0, "một", 0.0, 0.3),
            word(1, "hai", 2.0, 2.3),
        ]
        assert len(build_utterances(words, max_gap_s=5.0)) == 1

    def test_bounds_and_word_ids(self):
        words = [
            word(0, "a", 1.0, 1.2),
            word(1, "b", 1.2, 1.9),
        ]
        u = build_utterances(words)[0]
        assert u["start"] == pytest.approx(1.0)
        assert u["end"] == pytest.approx(1.9)
        assert u["word_ids"] == [0, 1]
        assert u["i"] == 0

    def test_no_speaker_field(self):
        u = build_utterances([word(0, "a", 0.0, 0.1)])[0]
        assert "speaker" not in u

    def test_utterance_indices_are_contiguous(self):
        words = [word(i, "x", i * 2.0, i * 2.0 + 0.2) for i in range(6)]
        utts = build_utterances(words)
        assert [u["i"] for u in utts] == list(range(len(utts)))

    def test_no_words_no_utterances(self):
        assert build_utterances([]) == []

    def test_every_word_id_appears_exactly_once(self):
        words = [word(i, "x", i * 0.4 + (i // 4) * 1.0, i * 0.4 + (i // 4) * 1.0 + 0.3)
                 for i in range(20)]
        ids = [i for u in build_utterances(words) for i in u["word_ids"]]
        assert ids == list(range(20))

    def test_text_is_a_plain_space_join_with_no_cleanup(self):
        """CLAUDE.md rule 1 — repetitions and fillers are the data."""
        words = [
            word(0, "à", 0.0, 0.1),
            word(1, "à", 0.1, 0.2),
            word(2, "ừ", 0.2, 0.3),
            word(3, "thì", 0.3, 0.4),
            word(4, "thì", 0.4, 0.5),
        ]
        assert build_utterances(words)[0]["text"] == "à à ừ thì thì"

    def test_word_without_end_uses_its_start(self):
        words = [word(0, "a", 0.0, None), word(1, "b", 0.3, 0.5)]
        assert len(build_utterances(words)) == 1

    def test_vad_segment_start_splits_without_a_gap(self):
        words = [word(0, "a", 0.0, 0.3), word(1, "b", 0.4, 0.7), word(2, "c", 0.8, 1.0)]
        utts = build_utterances(words, breaks=[0.0, 0.75])
        assert [u["text"] for u in utts] == ["a b", "c"]

    def test_break_before_the_first_word_does_not_split(self):
        words = [word(0, "a", 1.0, 1.3), word(1, "b", 1.4, 1.7)]
        assert len(build_utterances(words, breaks=[0.0, 0.5])) == 1

    def test_breaks_never_drop_or_reorder_words(self):
        words = [word(i, f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(40)]
        utts = build_utterances(words, breaks=[0.0, 2.05, 2.1, 7.0, 99.0])
        assert [i for u in utts for i in u["word_ids"]] == list(range(40))
        assert len(utts) == 3


class TestPassages:
    def test_short_pauses_stay_in_one_passage(self):
        assert passages([utt(0, 2), utt(2.8, 4), utt(5.4, 7)]) == [[0, 1, 2]]

    def test_long_pause_starts_a_new_passage(self):
        assert passages([utt(0, 2), utt(3.6, 5)]) == [[0], [1]]

    def test_pause_at_the_threshold_stays(self):
        assert passages([utt(0, 2), utt(3.5, 5)]) == [[0, 1]]

    def test_overlapping_utterances_do_not_break(self):
        # An utterance fully inside the previous one must not shorten the reference end.
        assert passages([utt(0, 10), utt(2, 3), utt(9.5, 11)]) == [[0, 1, 2]]

    def test_empty(self):
        assert passages([]) == []

    def test_every_index_once_in_order(self):
        items = [utt(i * 1.0 + (i % 3) * 2.0, i * 1.0 + (i % 3) * 2.0 + 0.5) for i in range(12)]
        assert [k for g in passages(items) for k in g] == list(range(12))
