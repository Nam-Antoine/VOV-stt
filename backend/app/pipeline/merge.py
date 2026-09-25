"""Group words into utterances, and utterances into passages (PLAN §3).

    Utterances: consecutive words with gap ≤ 0.5 s and no VAD segment start between
                them → one utterance
    Passages:   consecutive utterances with gap ≤ 1.5 s → one passage (the punctuation
                model's context; a paragraph never spans two)

There is no diarization: the transcript carries no speaker information at all.

This module is where a "tidy up the text" bug would be easiest to introduce and hardest
to notice. It must not: drop a word, reorder words, collapse a repeated word, insert
punctuation, or change casing. Utterance text is ``" ".join(word texts)`` and nothing
else (CLAUDE.md rule 1).

Pure python — no sherpa-onnx, no numpy — so the unit tests run anywhere.
"""

from __future__ import annotations

#: PLAN §3: consecutive words separated by more than this start a new utterance.
DEFAULT_MAX_GAP_S = 0.5

#: A pause longer than this between utterances starts a new passage. Radio talk pauses
#: briefly mid-thought; a hand-over or a new segment leaves a longer silence.
PASSAGE_GAP_S = 1.5


def build_utterances(words: list[dict], *, max_gap_s: float = DEFAULT_MAX_GAP_S,
                     breaks: list[float] | None = None) -> list[dict]:
    """Group words into utterances (PLAN §5 ``utterances`` block).

    A new utterance starts when the gap since the previous word's ``end`` exceeds
    ``max_gap_s``, or when a time in ``breaks`` (the VAD segment starts: silences the
    VAD found, at most 25 s apart) falls after the previous word's start and at or
    before this word's start. Word timings alone rarely show a 0.5 s gap in radio talk,
    so without ``breaks`` an utterance can run for minutes. ``text`` is the words joined
    by single spaces — no punctuation, no capitalisation, no dedupe of repeated words.
    """
    utterances: list[dict] = []
    cur: dict | None = None
    prev_end: float | None = None
    prev_start: float | None = None
    marks = sorted(breaks or [])
    k = 0

    for w in words:
        start = float(w["start"])
        end = float(w["end"]) if w.get("end") is not None else start
        gap = start - prev_end if prev_end is not None else 0.0
        crossed = False
        while k < len(marks) and marks[k] <= start:
            crossed = crossed or (prev_start is not None and marks[k] > prev_start)
            k += 1

        if cur is None or gap > max_gap_s or crossed:
            if cur is not None:
                utterances.append(cur)
            cur = {
                "i": len(utterances),
                "start": start,
                "end": end,
                "word_ids": [],
                "_texts": [],
            }
        cur["word_ids"].append(int(w["i"]))
        cur["_texts"].append(w["text"])
        cur["end"] = max(cur["end"], end)
        prev_end = end
        prev_start = start

    if cur is not None:
        utterances.append(cur)

    for u in utterances:
        # Verbatim: join only. Do not strip, title-case, or punctuate.
        u["text"] = " ".join(u.pop("_texts"))
    return utterances


def passages(utterances: list[dict], *, max_gap_s: float = PASSAGE_GAP_S) -> list[list[int]]:
    """Indices of consecutive utterances with no pause longer than ``max_gap_s``.

    Each item needs ``start`` and ``end`` (seconds). A grouping only: no text is read.
    """
    groups: list[list[int]] = []
    prev_end: float | None = None
    for k, u in enumerate(utterances):
        start = float(u["start"])
        if groups and prev_end is not None and start - prev_end <= max_gap_s:
            groups[-1].append(k)
        else:
            groups.append([k])
        end = float(u["end"]) if u.get("end") is not None else start
        prev_end = end if prev_end is None else max(prev_end, end)
    return groups
