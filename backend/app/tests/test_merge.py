"""Speaker assignment and utterance grouping (PLAN §3).

Merge is the last stage before the immutable raw JSON, so a word lost here is lost for
good. These tests pin: max-overlap wins, the nearest-segment fallback, -1 when there is
nothing to fall back to, and that grouping never drops, reorders or rewrites a word.
"""

from __future__ import annotations

import pytest

from app.pipeline.merge import (
    UNKNOWN_SPEAKER,
    assign_speakers,
    build_utterances,
    merge,
    snap_to_pauses,
)


def word(i, text, start, end, speaker=None):
    w = {"i": i, "text": text, "start": start, "end": end, "conf": None}
    if speaker is not None:
        w["speaker"] = speaker
    return w


def seg(start, end, speaker):
    return {"start": start, "end": end, "speaker": speaker}


class TestAssignSpeakers:
    def test_max_overlap_wins(self):
        words = [word(0, "a", 1.0, 2.0)]
        # 0.4 s inside cluster 0, 0.6 s inside cluster 1 → cluster 1.
        assign_speakers(words, [seg(0.0, 1.4, 0), seg(1.4, 5.0, 1)])
        assert words[0]["speaker"] == 1

    def test_word_fully_inside_one_segment(self):
        words = [word(0, "a", 2.0, 2.5)]
        assign_speakers(words, [seg(0.0, 1.0, 0), seg(1.5, 3.0, 7)])
        assert words[0]["speaker"] == 7

    def test_word_in_a_diarization_gap_takes_the_nearest_segment(self):
        """A word between two spans still belongs to somebody."""
        words = [word(0, "à", 5.05, 5.15)]
        assign_speakers(words, [seg(0.0, 5.0, 3), seg(9.0, 12.0, 4)])
        assert words[0]["speaker"] == 3

    def test_no_segments_means_unknown_not_cluster_zero(self):
        words = [word(0, "a", 0.0, 1.0), word(1, "b", 1.0, 2.0)]
        assign_speakers(words, [])
        assert [w["speaker"] for w in words] == [UNKNOWN_SPEAKER, UNKNOWN_SPEAKER]

    def test_zero_length_word_is_placed_by_position(self):
        words = [word(0, "ừ", 3.0, 3.0)]
        assign_speakers(words, [seg(0.0, 2.0, 0), seg(2.5, 4.0, 1)])
        assert words[0]["speaker"] == 1

    def test_unordered_segments_are_handled(self):
        words = [word(0, "a", 6.0, 6.5)]
        assign_speakers(words, [seg(5.0, 8.0, 2), seg(0.0, 4.0, 1)])
        assert words[0]["speaker"] == 2

    def test_every_word_gets_a_speaker(self):
        words = [word(i, "x", i * 0.5, i * 0.5 + 0.4) for i in range(10)]
        assign_speakers(words, [seg(0.0, 2.0, 0), seg(2.0, 6.0, 1)])
        assert all("speaker" in w for w in words)


class TestBuildUtterances:
    def test_speaker_change_starts_a_new_utterance(self):
        words = [
            word(0, "một", 0.0, 0.3, speaker=0),
            word(1, "hai", 0.3, 0.6, speaker=0),
            word(2, "ba", 0.6, 0.9, speaker=1),
        ]
        utts = build_utterances(words)
        assert [u["speaker"] for u in utts] == [0, 1]
        assert [u["text"] for u in utts] == ["một hai", "ba"]

    def test_gap_over_the_threshold_starts_a_new_utterance(self):
        words = [
            word(0, "một", 0.0, 0.3, speaker=0),
            word(1, "hai", 1.0, 1.3, speaker=0),   # 0.7 s gap > 0.5 s
        ]
        assert len(build_utterances(words)) == 2

    def test_gap_at_the_threshold_stays_in_one_utterance(self):
        words = [
            word(0, "một", 0.0, 0.3, speaker=0),
            word(1, "hai", 0.8, 1.1, speaker=0),   # exactly 0.5 s
        ]
        assert len(build_utterances(words)) == 1

    def test_max_gap_is_configurable(self):
        words = [
            word(0, "một", 0.0, 0.3, speaker=0),
            word(1, "hai", 2.0, 2.3, speaker=0),
        ]
        assert len(build_utterances(words, max_gap_s=5.0)) == 1

    def test_bounds_and_word_ids(self):
        words = [
            word(0, "a", 1.0, 1.2, speaker=0),
            word(1, "b", 1.2, 1.9, speaker=0),
        ]
        u = build_utterances(words)[0]
        assert u["start"] == pytest.approx(1.0)
        assert u["end"] == pytest.approx(1.9)
        assert u["word_ids"] == [0, 1]
        assert u["i"] == 0

    def test_utterance_indices_are_contiguous(self):
        words = [word(i, "x", i * 2.0, i * 2.0 + 0.2, speaker=i % 2) for i in range(6)]
        utts = build_utterances(words)
        assert [u["i"] for u in utts] == list(range(len(utts)))

    def test_no_words_no_utterances(self):
        assert build_utterances([]) == []

    def test_every_word_id_appears_exactly_once(self):
        words = [word(i, "x", i * 0.4, i * 0.4 + 0.3, speaker=i // 4) for i in range(20)]
        ids = [i for u in build_utterances(words) for i in u["word_ids"]]
        assert ids == list(range(20))

    def test_text_is_a_plain_space_join_with_no_cleanup(self):
        """CLAUDE.md rule 1 — repetitions and fillers are the data."""
        words = [
            word(0, "à", 0.0, 0.1, speaker=0),
            word(1, "à", 0.1, 0.2, speaker=0),
            word(2, "ừ", 0.2, 0.3, speaker=0),
            word(3, "thì", 0.3, 0.4, speaker=0),
            word(4, "thì", 0.4, 0.5, speaker=0),
        ]
        assert build_utterances(words)[0]["text"] == "à à ừ thì thì"

    def test_unknown_speaker_groups_like_any_other_cluster(self):
        words = [
            word(0, "a", 0.0, 0.1, speaker=UNKNOWN_SPEAKER),
            word(1, "b", 0.1, 0.2, speaker=UNKNOWN_SPEAKER),
        ]
        utts = build_utterances(words)
        assert len(utts) == 1 and utts[0]["speaker"] == UNKNOWN_SPEAKER


class TestMerge:
    def test_end_to_end_ordering(self):
        words = [
            word(0, "kính", 0.5, 0.7),
            word(1, "chào", 0.7, 1.0),
            word(2, "vâng", 4.0, 4.3),
        ]
        segments = [seg(0.0, 2.0, 0), seg(3.5, 5.0, 1)]
        out_words, utts = merge(words, segments)
        assert [w["speaker"] for w in out_words] == [0, 0, 1]
        assert [u["text"] for u in utts] == ["kính chào", "vâng"]

    def test_merge_preserves_the_word_list_length(self):
        words = [word(i, f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(50)]
        out_words, utts = merge(words, [seg(0.0, 20.0, 0)])
        assert len(out_words) == 50
        assert sum(len(u["word_ids"]) for u in utts) == 50


# --- snapping speaker changes to VAD pauses ------------------------------------------
# Real case ("Khủng hoảng tuổi 30"): the diarizer put the change 0.5 s late, so the
# next speaker's "khi mà" stayed with the host; the VAD pause sits on the real change.

HOST_THEN_CALLER = [
    word(0, "cùng", 73.13, 73.33), word(1, "nghe", 73.33, 73.51),
    word(2, "khi", 73.51, 73.67), word(3, "mà", 73.67, 73.95),
    word(4, "bản", 73.95, 74.11), word(5, "thân", 74.11, 74.31),
]


def test_a_late_change_moves_back_to_the_pause():
    segments = [seg(61.1, 74.03, 2), seg(74.03, 96.03, 3)]
    out, utts = merge([dict(w) for w in HOST_THEN_CALLER], segments,
                      pauses=[60.96, 71.13, 73.51, 90.08])
    assert [u["text"] for u in utts] == ["cùng nghe", "khi mà bản thân"]
    assert [u["speaker"] for u in utts] == [2, 3]


def test_without_pauses_nothing_moves():
    segments = [seg(61.1, 74.03, 2), seg(74.03, 96.03, 3)]
    _, utts = merge([dict(w) for w in HOST_THEN_CALLER], segments)
    assert utts[0]["text"].startswith("cùng nghe khi mà")   # the old, wrong split


def test_a_small_first_piece_does_not_block_the_snap():
    # 3 -> 4 at 96.03, but 4's first piece ends at 96.94, before the 97.06 pause.
    got = snap_to_pauses([seg(74.03, 96.03, 3), seg(96.03, 96.94, 4), seg(97.53, 118.04, 4)],
                         [90.08, 97.06, 114.88])
    assert got == [seg(74.03, 97.06, 3), seg(97.06, 118.04, 4)]


def test_a_pause_too_far_away_is_ignored():
    got = snap_to_pauses([seg(0.0, 10.0, 0), seg(10.0, 20.0, 1)], [5.0, 15.0])
    assert got == [seg(0.0, 10.0, 0), seg(10.0, 20.0, 1)]


def test_snapping_never_drops_or_rewrites_a_word():
    words = [word(i, f"w{i}", i * 0.3, i * 0.3 + 0.3) for i in range(60)]
    segments = [seg(0.0, 6.2, 0), seg(6.2, 12.4, 1), seg(12.4, 18.0, 0)]
    out, utts = merge([dict(w) for w in words], segments, pauses=[5.7, 13.0])
    assert [w["text"] for w in out] == [f"w{i}" for i in range(60)]
    assert " ".join(u["text"] for u in utts) == " ".join(f"w{i}" for i in range(60))
