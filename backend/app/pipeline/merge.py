"""Attach speakers to words, then group words into utterances (PLAN §3).

    Merge:      each word gets the diarization segment with max overlap
                (else the nearest segment, else -1)
    Utterances: consecutive words, same speaker, gap ≤ 0.5 s → one utterance

This module is where a "tidy up the text" bug would be easiest to introduce and hardest
to notice. It must not: drop a word, reorder words, collapse a repeated word, insert
punctuation, or change casing. Utterance text is ``" ".join(word texts)`` and nothing
else (CLAUDE.md rule 1).

Pure python — no sherpa-onnx, no numpy — so the unit tests run anywhere.
"""

from __future__ import annotations

#: Words with no overlapping and no nearby diarization segment.
UNKNOWN_SPEAKER = -1

#: PLAN §3: consecutive words of one speaker separated by more than this start a new
#: utterance.
DEFAULT_MAX_GAP_S = 0.5


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _distance(word_start: float, word_end: float, seg: dict) -> float:
    """Gap between a word and a segment; 0.0 when they touch or overlap."""
    if word_end < seg["start"]:
        return seg["start"] - word_end
    if word_start > seg["end"]:
        return word_start - seg["end"]
    return 0.0


def assign_speakers(words: list[dict], segments: list[dict],
                    *, unknown: int = UNKNOWN_SPEAKER) -> list[dict]:
    """Set ``word["speaker"]`` from the diarization segments, in place, and return it.

    Max overlap wins. A word that overlaps nothing takes the speaker of the nearest
    segment — a word between two diarization spans still belongs to somebody. With no
    segments at all, every word gets ``unknown`` rather than a fabricated cluster 0.
    """
    if not segments:
        for w in words:
            w["speaker"] = unknown
        return words

    ordered = sorted(segments, key=lambda s: (s["start"], s["end"]))
    for w in words:
        start = float(w["start"])
        end = float(w["end"]) if w.get("end") is not None else start
        best_seg, best_overlap = None, 0.0
        for seg in ordered:
            if seg["start"] > end:
                break
            ov = _overlap(start, end, seg["start"], seg["end"])
            if ov > best_overlap:
                best_seg, best_overlap = seg, ov
        if best_seg is None:
            best_seg = min(ordered, key=lambda s: _distance(start, end, s))
        w["speaker"] = int(best_seg["speaker"])
    return words


def build_utterances(words: list[dict], *, max_gap_s: float = DEFAULT_MAX_GAP_S) -> list[dict]:
    """Group words into utterances (PLAN §5 ``utterances`` block).

    A new utterance starts when the speaker changes or the gap since the previous word's
    ``end`` exceeds ``max_gap_s``. ``text`` is the words joined by single spaces — no
    punctuation, no capitalisation, no dedupe of repeated words.
    """
    utterances: list[dict] = []
    cur: dict | None = None
    prev_end: float | None = None

    for w in words:
        speaker = int(w.get("speaker", UNKNOWN_SPEAKER))
        start = float(w["start"])
        end = float(w["end"]) if w.get("end") is not None else start
        gap = start - prev_end if prev_end is not None else 0.0

        if cur is None or speaker != cur["speaker"] or gap > max_gap_s:
            if cur is not None:
                utterances.append(cur)
            cur = {
                "i": len(utterances),
                "speaker": speaker,
                "start": start,
                "end": end,
                "word_ids": [],
                "_texts": [],
            }
        cur["word_ids"].append(int(w["i"]))
        cur["_texts"].append(w["text"])
        cur["end"] = max(cur["end"], end)
        prev_end = end

    if cur is not None:
        utterances.append(cur)

    for u in utterances:
        # Verbatim: join only. Do not strip, title-case, or punctuate.
        u["text"] = " ".join(u.pop("_texts"))
    return utterances


def merge(words: list[dict], segments: list[dict],
          *, max_gap_s: float = DEFAULT_MAX_GAP_S) -> tuple[list[dict], list[dict]]:
    """Run both stages: speaker assignment then utterance grouping."""
    words = assign_speakers(words, segments)
    return words, build_utterances(words, max_gap_s=max_gap_s)
