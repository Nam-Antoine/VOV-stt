"""Readable layer: punctuation and capitalisation restored by ViBERT-capu.

This is a **separate, derived layer**. It never touches the corpus text (CLAUDE.md
rule 1): ``utterances.text_asr`` and ``text_verified`` stay exactly as spoken and are
what every corpus export carries. The readable text lives in its own column and its own
exports (``readable.docx``, ``readable.txt``), for people who want to *read* the
programme, like the client's reference document.

Model: ``welcomyou/vibert-capu-onnx`` (ONNX export of ``dragonSwing/vibert-capu``,
CC BY-SA 4.0), a GECToR-style token tagger. For each word it predicts one edit action.
Only two kinds are accepted here:

* append ``,`` ``.`` ``:`` ``?`` after the word
* change the word's case (Capital / UPPER / lower)

Everything else the model can emit — ``$MERGE_SPACE`` (joins two words), verb-form
transforms — is refused, and :func:`restore` checks after every turn that the words,
case-folded, are exactly the input words in the same order. A turn that fails the check
falls back to its verbatim text. Fillers, repetitions and false starts therefore survive
by construction: a tagger that can only add marks and change case cannot drop them.

Inference mirrors the upstream ``gec_model.py``: a ``$START`` token is prepended, input
is lower-cased, words are processed in 48-word chunks with 12 words of overlap, and the
tagging is iterated up to 3 times (a word can get only one action per pass, so a full
stop in one pass lets the next pass capitalise the word after it). Each pass runs over
the *whole* turn and every word takes its result from the chunk where it sits furthest
from an edge, so chunk boundaries never disagree about a sentence end.

Context is a *turn* (consecutive utterances of one speaker), not an utterance: VAD
splits mid-sentence, and the model needs the words on both sides to place a full stop.
The punctuated turn is then cut back into utterances by word count.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MARKS = (",", ".", ":", "?")
_MARK_SET = frozenset(MARKS)
_APPEND = {f"$APPEND_{m}": m for m in MARKS}
_CASE = {"$TRANSFORM_CASE_CAPITAL", "$TRANSFORM_CASE_UPPER", "$TRANSFORM_CASE_LOWER"}


@dataclass(frozen=True)
class ModelSpec:
    """One tagger. ``kind`` picks its tokeniser: ``wordpiece`` (ViBERT, BERT vocab.txt)
    or ``sentencepiece`` (XLM-R, sentencepiece.bpe.model with the fairseq +1 offset)."""

    dir: Path
    file: str
    kind: str = "wordpiece"
    weight: float = 1.0


@dataclass(frozen=True)
class PunctParams:
    #: One model, or several whose per-word probabilities are averaged by weight
    #: (the upstream Capu ensemble).
    models: tuple[ModelSpec, ...] = ()
    num_threads: int = 2
    iterations: int = 3
    chunk_words: int = 48
    overlap_words: int = 12
    #: Subtracted from log P($KEEP): >0 makes the tagger readier to add a mark or a
    #: capital. Chosen on the tuning half of the client's reference (see
    #: scripts/punct_eval.py); 0 is the model's own calibration.
    keep_bias: float = 0.0
    #: Added to log P($APPEND_.): >0 turns more of the model's commas into sentence
    #: ends. The model under-splits radio speech (on the reference: sentence-end
    #: precision ~85 %, recall ~60 %; comma precision ~52 %), so a positive value
    #: moves it toward the reference's one-sentence-per-line style.
    stop_bias: float = 0.0

    def as_json(self) -> dict:
        return {
            "models": [{"file": m.file, "weight": m.weight} for m in self.models],
            "iterations": self.iterations,
            "chunk_words": self.chunk_words,
            "overlap_words": self.overlap_words,
            "keep_bias": self.keep_bias,
            "stop_bias": self.stop_bias,
        }


def _apply_case(word: str, action: str) -> str:
    if action == "$TRANSFORM_CASE_CAPITAL":
        return word[:1].upper() + word[1:]
    if action == "$TRANSFORM_CASE_UPPER":
        return word.upper()
    return word.lower()


@dataclass
class _Head:
    """One loaded ONNX tagger and its tokeniser."""

    spec: ModelSpec
    session: object
    labels: list[str]
    start_id: int
    encode: object          # word -> list[int]
    token_types: bool       # whether the graph takes token_type_ids

    @classmethod
    def load(cls, spec: ModelSpec, num_threads: int) -> _Head:
        import onnxruntime as ort

        d = spec.dir
        labels = (d / "vocabulary" / "labels.txt").read_text(encoding="utf-8").split()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = num_threads
        opts.inter_op_num_threads = 1
        session = ort.InferenceSession(str(d / spec.file), opts,
                                       providers=["CPUExecutionProvider"])
        token_types = any(i.name == "token_type_ids" for i in session.get_inputs())
        if spec.kind == "wordpiece":
            vocab = (d / "vocab.txt").read_text(encoding="utf-8").split("\n")
            index = {w: i for i, w in enumerate(vocab)}
            unk = index["[UNK]"]

            def encode(word: str) -> list[int]:
                return _wordpiece(word, index, unk)

            # Upstream: tokenizer.add_tokens(["$START"]) -> the next free id.
            start = len(vocab)
        elif spec.kind == "sentencepiece":
            import sentencepiece as spm

            sp = spm.SentencePieceProcessor(model_file=str(d / "sentencepiece.bpe.model"))
            sp_unk = sp.unk_id()

            def encode(word: str) -> list[int]:
                # XLMRobertaTokenizer: fairseq ids are spm ids + 1; <unk> is 3.
                ids = [3 if i == sp_unk else i + 1 for i in sp.encode(word)]
                return ids or [3]

            start = sp.get_piece_size() + 1 + 1  # len(tokenizer) before $START: spm + <mask>
        else:
            raise ValueError(f"unknown tokeniser kind {spec.kind!r}")
        log.info("punctuate: loaded %s (%s)", spec.file, spec.kind)
        return cls(spec=spec, session=session, labels=labels, start_id=start,
                   encode=encode, token_types=token_types)

    def probs(self, tokens: list[str]):
        """Per-token softmax over the labels, ``$START`` slot included."""
        import numpy as np

        ids, offsets = [self.start_id], [0]
        for t in tokens:
            offsets.append(len(ids))
            ids.extend(self.encode(t))
        n = len(ids)
        feed = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.ones((1, n), dtype=np.int64),
            "input_offsets": np.array([offsets], dtype=np.int64),
        }
        if self.token_types:
            feed["token_type_ids"] = np.zeros((1, n), dtype=np.int64)
        logits = self.session.run(None, feed)[0][0].astype(np.float64)
        logits -= logits.max(-1, keepdims=True)
        e = np.exp(logits)
        return e / e.sum(-1, keepdims=True)


def _wordpiece(word: str, index: dict[str, int], unk: int) -> list[int]:
    """BertTokenizer(do_basic_tokenize=False) on one word: greedy longest-match."""
    ids, start = [], 0
    while start < len(word):
        end, cur = len(word), None
        while start < end:
            sub = word[start:end] if start == 0 else "##" + word[start:end]
            if sub in index:
                cur = index[sub]
                break
            end -= 1
        if cur is None:
            return [unk]
        ids.append(cur)
        start = end
    return ids or [unk]


_ALLOWED = {"$KEEP", *_APPEND, *_CASE}


@dataclass
class Punctuator:
    """Loaded tagger(s). Thread-safe for :meth:`restore` (onnxruntime sessions are)."""

    params: PunctParams
    _heads: list[_Head] = field(repr=False, default_factory=list)
    _labels: list[str] = field(repr=False, default_factory=list)

    @classmethod
    def load(cls, params: PunctParams) -> Punctuator:
        heads = [_Head.load(m, params.num_threads) for m in params.models]
        labels = heads[0].labels
        if any(h.labels != labels for h in heads):
            raise ValueError("ensemble members disagree on the label set")
        return cls(params=params, _heads=heads, _labels=labels)

    def _predict(self, tokens: list[str]) -> list[str]:
        """One action label per token (the ``$START`` slot is dropped).

        Weighted mean of the members' probabilities, the ``$KEEP`` bias, then the best
        *accepted* action — a refused action (merge, verb form) can never win.
        """
        import numpy as np

        total = sum(h.spec.weight for h in self._heads)
        probs = sum(h.spec.weight * h.probs(tokens) for h in self._heads) / total
        logp = np.log(np.maximum(probs, 1e-12))
        keep = self._labels.index("$KEEP")
        logp[:, keep] -= self.params.keep_bias
        logp[:, self._labels.index("$APPEND_.")] += self.params.stop_bias
        refused = [k for k, lab in enumerate(self._labels) if lab not in _ALLOWED]
        logp[:, refused] = -np.inf
        return [self._labels[k] for k in logp.argmax(-1)][1:]

    # --- tagging passes ---

    def _one_pass(self, groups: list[list[str]]) -> list[list[str]]:
        """``groups[i]`` is word i followed by the marks already attached to it.

        Walks the groups, not the flat token list, so the word count can never change.
        """
        actions = self._predict([t for g in groups for t in g])
        out: list[list[str]] = []
        pos = 0
        for g in groups:
            action = actions[pos]
            pos += len(g)
            word = g[0]
            if not strip_marks(word):          # a bare mark a verifier typed
                out.append(list(g))
                continue
            if action in _CASE:
                word = _apply_case(word, action)
            new = [word, *g[1:]]
            mark = _APPEND.get(action)
            if mark and len(g) == 1:           # never a second mark
                new.append(mark)
            out.append(new)
        return out

    def _chunked_pass(self, groups: list[list[str]]) -> list[list[str]]:
        chunk, overlap = self.params.chunk_words, self.params.overlap_words
        if len(groups) <= chunk:
            return self._one_pass(groups)
        starts = list(range(0, len(groups) - overlap, chunk - overlap))
        results = [(s, self._one_pass(groups[s:s + chunk])) for s in starts]
        merged = []
        for i in range(len(groups)):
            best, score = None, -1
            for s, out in results:
                if s <= i < s + len(out):
                    d = min(i - s, s + len(out) - 1 - i)
                    if d > score:
                        best, score = out[i - s], d
            merged.append(best)
        return merged

    def restore(self, words: list[str]) -> list[str]:
        """Punctuated, cased copies of ``words``: same words, same order, one each.

        ``result[i]`` is ``words[i]`` with its case possibly changed and at most one
        mark appended. If the model output fails that contract, the input comes back
        unchanged.
        """
        if not words:
            return []
        # A verifier may have typed marks already; they ride along as attached tokens,
        # so the model sees them and does not add a second one.
        groups = []
        for w in words:
            core = strip_marks(w)
            if not core:
                groups.append([w])
                continue
            groups.append([core.lower(), *w[len(core):]])
        for _ in range(self.params.iterations):
            new = self._chunked_pass(groups)
            if new == groups:
                break
            groups = new
        # Sentence case: a stop added in the last pass had no later pass in which the
        # model could capitalise the next word. Case only; the word is unchanged.
        for k in range(1, len(groups)):
            if groups[k - 1][-1] in (".", "?") and groups[k][0][:1].islower():
                groups[k] = [groups[k][0][:1].upper() + groups[k][0][1:], *groups[k][1:]]
        out = ["".join(g) for g in groups]
        if not same_words(words, out):
            log.warning("punctuate: model output changed the words; keeping verbatim")
            return list(words)
        return out


def strip_marks(token: str) -> str:
    while token and token[-1] in _MARK_SET:
        token = token[:-1]
    return token


def same_words(src: list[str], out: list[str]) -> bool:
    """The verbatim contract: only case and trailing marks may differ."""
    if len(src) != len(out):
        return False
    return all(
        strip_marks(o).lower() == strip_marks(s).lower()
        for s, o in zip(src, out, strict=True)
    )


def turns(utterances: list[dict]) -> list[list[int]]:
    """Indices of consecutive same-speaker utterances."""
    groups: list[list[int]] = []
    for k, u in enumerate(utterances):
        if groups and utterances[groups[-1][-1]]["speaker"] == u["speaker"]:
            groups[-1].append(k)
        else:
            groups.append([k])
    return groups


def readable_turn(punctuator: Punctuator, texts: list[str]) -> list[str]:
    """Punctuate one speaker turn given its utterance texts; one string per utterance.

    Whitespace inside an utterance is kept exactly where there is no mark to add, since
    only the words' own characters change.
    """
    split = [t.split() for t in texts]
    flat = [w for ws in split for w in ws]
    restored = punctuator.restore(flat)
    out, k = [], 0
    for text, ws in zip(texts, split, strict=True):
        if not ws:
            out.append(text)
            continue
        seg = restored[k:k + len(ws)]
        # The engine writes all capitals, so anything else was typed by a verifier:
        # their "Hà Nội" or "VOV2" stands; the model only decides the lower-case words.
        if text != text.upper():
            seg = [_keep_typed_case(w, r) for w, r in zip(ws, seg, strict=True)]
        out.append(_rejoin(text, ws, seg))
        k += len(ws)
    # Capitalise the first word of a turn: it is the start of a sentence by definition.
    for idx, t in enumerate(out):
        if t.strip():
            lead = len(t) - len(t.lstrip())
            out[idx] = t[:lead] + t[lead:lead + 1].upper() + t[lead + 1:]
            break
    return out


def _keep_typed_case(typed: str, restored: str) -> str:
    """``restored`` with ``typed``'s casing, unless the typed word was all lower case."""
    core = strip_marks(typed)
    if core == core.lower():
        return restored
    return core + restored[len(strip_marks(restored)):]


def _rejoin(text: str, words: list[str], restored: list[str]) -> str:
    """Put ``restored`` back into ``text`` in place of ``words``, keeping the spacing."""
    pieces, pos = [], 0
    for w, r in zip(words, restored, strict=True):
        at = text.index(w, pos)
        pieces.append(text[pos:at])
        pieces.append(r)
        pos = at + len(w)
    pieces.append(text[pos:])
    return "".join(pieces)


def sentences(text: str) -> list[str]:
    """Split readable text into sentences at ``.`` or ``?`` followed by a space."""
    out, cur = [], []
    for tok in text.split():
        cur.append(tok)
        if tok[-1] in ".?":
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out



_cached: Punctuator | None = None
_lock = threading.Lock()


def get(params: PunctParams) -> Punctuator:
    """Process-wide model, loaded on first use (≈450 MB, ~2 s)."""
    global _cached
    with _lock:
        if _cached is None or _cached.params != params:
            _cached = Punctuator.load(params)
        return _cached
