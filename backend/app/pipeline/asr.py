"""Zipformer-30M RNN-T via sherpa-onnx (PLAN §2.1, §2.2).

The engine emits lowercase text with no punctuation and no casing. That is exactly what a
verbatim corpus wants. **Nothing in this module may alter the text the engine returns** —
no strip, no casefold, no dedupe, no filler removal (CLAUDE.md rule 1).

Word boundaries come from the BPE tokens, not from spaces in the text: a word starts at
the token carrying the sentencepiece word-boundary marker. Splitting the *text* on spaces
glues syllables together (PLAN §13).

One deviation from PLAN §2.2, verified against sherpa-onnx 1.13.8 on 22 Sep 2026: the
Python bindings return tokens with the marker already rendered as an ASCII space
(``' RỒI'``, ``' CŨNG'``), not as ``▁``. Testing only for ``▁`` — as the plan's reference
code does — collapses an entire segment into one "word". :data:`WORD_MARKERS` therefore
accepts both, and :func:`tokens_to_words` is otherwise the plan's algorithm unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: sentencepiece word-boundary marker (U+2581), not an ASCII underscore.
WORD_PREFIX = "▁"

#: Both spellings of the word-boundary marker. sherpa-onnx 1.13.8 emits the space form;
#: older builds and other model exports emit ``▁``. See the module docstring.
WORD_MARKERS = (WORD_PREFIX, " ")


def is_word_start(token: str) -> bool:
    """True when this BPE token opens a new word."""
    return token.startswith(WORD_MARKERS)


def strip_marker(token: str) -> str:
    """Remove the word-boundary marker. De-tokenisation, not normalisation."""
    return token[1:] if is_word_start(token) else token


def ensure_bpe_vocab(model_dir: str, cache_dir: str | None = None) -> str:
    """Return a path to a text BPE vocab, generating it from ``bpe.model`` if needed.

    PLAN §2 says to pass ``bpe_vocab=bpe.model`` for hotwords. sherpa-onnx 1.13.8 does
    not accept the sentencepiece binary there — it wants a text file of
    ``<piece> <score>`` per line and otherwise fails with "Each line in vocab should
    contain two items". So we export one from the model.

    This is a *format conversion of the tokenizer*, not of any transcript text, so it
    carries no verbatim risk. The file is written next to the model when that directory
    is writable, else into ``cache_dir`` — in the container ``models/`` is mounted
    read-only on purpose.
    """
    model_path = Path(model_dir) / "bpe.model"
    if not model_path.exists():
        raise FileNotFoundError(f"{model_path} missing — run `make models`")

    for candidate in (Path(model_dir) / "bpe.vocab",
                      Path(cache_dir or model_dir) / "bpe.vocab"):
        if candidate.exists():
            return str(candidate)

    import sentencepiece as spm

    sp = spm.SentencePieceProcessor(model_file=str(model_path))
    body = "".join(
        f"{sp.id_to_piece(i)} {sp.get_score(i)}\n" for i in range(sp.get_piece_size())
    )

    for target in (Path(model_dir) / "bpe.vocab",
                   Path(cache_dir) / "bpe.vocab" if cache_dir else None):
        if target is None:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            log.info("wrote BPE vocab for hotwords: %s (%d pieces)",
                     target, sp.get_piece_size())
            return str(target)
        except OSError:
            continue  # read-only mount; try the cache dir
    raise OSError(
        f"could not write a BPE vocab into {model_dir!r} or {cache_dir!r}; "
        "hotwords need one (see CLAUDE.md rule 5)"
    )


@dataclass(frozen=True)
class AsrParams:
    """PLAN §2 author defaults. ``blank_penalty`` and decoding are swept in the pilot."""

    model_dir: str
    int8: bool = True
    num_threads: int = 3
    sample_rate: int = 16_000
    feature_dim: int = 80
    blank_penalty: float = 0.25
    decoding_method: str = "modified_beam_search"
    max_active_paths: int = 4
    hotwords_file: str | None = None
    hotwords_score: float = 1.5
    epoch_tag: str = "epoch-20-avg-10"
    #: Where a generated bpe.vocab may be written when model_dir is read-only.
    vocab_cache_dir: str | None = None

    def model_files(self) -> dict[str, str]:
        sfx = ".int8.onnx" if self.int8 else ".onnx"
        return {
            "encoder": f"encoder-{self.epoch_tag}{sfx}",
            "decoder": f"decoder-{self.epoch_tag}{sfx}",
            "joiner": f"joiner-{self.epoch_tag}{sfx}",
            "tokens": "tokens.txt",
            "bpe_vocab": "bpe.model",
        }

    def as_json(self, *, hotwords_sha256: str | None = None) -> dict:
        """The ``engine.params`` block of the raw JSON (PLAN §5)."""
        d = {
            "decoding_method": self.decoding_method,
            "max_active_paths": self.max_active_paths,
            "blank_penalty": self.blank_penalty,
            "hotwords_score": self.hotwords_score if self.hotwords_file else None,
            "hotwords_sha256": hotwords_sha256,
            "int8": self.int8,
            "num_threads": self.num_threads,
        }
        return d


def load_recognizer(model_dir: str, *, int8: bool = True, threads: int = 3,
                    hotwords_file: str | None = None, hotwords_score: float = 1.5,
                    blank_penalty: float = 0.25,
                    decoding_method: str = "modified_beam_search",
                    max_active_paths: int = 4, epoch_tag: str = "epoch-20-avg-10",
                    vocab_cache_dir: str | None = None):
    """Build an ``OfflineRecognizer`` (PLAN §2.1, from the author's demo Space).

    Hotwords require ``modified_beam_search`` — greedy silently ignores them
    (CLAUDE.md rule 5, PLAN §13), so we refuse the combination rather than produce a
    transcript that quietly lacks the biasing the caller asked for.
    """
    import sherpa_onnx

    sfx = ".int8.onnx" if int8 else ".onnx"
    kwargs = dict(
        tokens=f"{model_dir}/tokens.txt",          # the file HF calls config.json
        encoder=f"{model_dir}/encoder-{epoch_tag}{sfx}",
        decoder=f"{model_dir}/decoder-{epoch_tag}{sfx}",
        joiner=f"{model_dir}/joiner-{epoch_tag}{sfx}",
        num_threads=threads,
        sample_rate=16000,
        feature_dim=80,
        blank_penalty=blank_penalty,                # author's default; see PLAN §4.3
        decoding_method=decoding_method,            # required for hotwords
        max_active_paths=max_active_paths,
    )
    if hotwords_file:
        if decoding_method != "modified_beam_search":
            raise ValueError(
                "hotwords need decoding_method='modified_beam_search' "
                f"(got {decoding_method!r}) — see CLAUDE.md rule 5"
            )
        kwargs.update(hotwords_file=hotwords_file, hotwords_score=hotwords_score,
                      modeling_unit="bpe",
                      bpe_vocab=ensure_bpe_vocab(model_dir, vocab_cache_dir))
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs)


def recognizer_from_params(params: AsrParams):
    """``load_recognizer`` driven by an :class:`AsrParams`."""
    return load_recognizer(
        params.model_dir, int8=params.int8, threads=params.num_threads,
        hotwords_file=params.hotwords_file, hotwords_score=params.hotwords_score,
        blank_penalty=params.blank_penalty, decoding_method=params.decoding_method,
        max_active_paths=params.max_active_paths, epoch_tag=params.epoch_tag,
        vocab_cache_dir=params.vocab_cache_dir,
    )


def transcribe_segment(rec, samples_f32, sr=16000):
    """Decode one segment. Returns the engine's own strings, untouched (PLAN §2.1)."""
    s = rec.create_stream()
    s.accept_waveform(sr, samples_f32)
    rec.decode_stream(s)
    r = s.result
    return {"text": r.text, "tokens": list(r.tokens), "timestamps": list(r.timestamps),
            "logprobs": list(getattr(r, "ys_log_probs", []) or [])}


def tokens_to_words(tokens, timestamps, logprobs, offset_s, seg_end_s):
    """Roll BPE tokens up into words with absolute timestamps (PLAN §2.2).

    A word starts at a token carrying the word-boundary marker (``▁`` or, in
    sherpa-onnx 1.13.8, a leading space). Vietnamese is monosyllabic in orthography, so
    each marked group is roughly one syllable-word.

    ``end`` is the next word's ``start``, because RNN-T emits at token *start*. That is
    an approximation, good to the ±200 ms click-to-play target. PLAN §2.2: do not try to
    be cleverer.

    ``conf`` is the mean log-prob over the word's tokens — lower is worse, and it is
    ``None`` when the installed sherpa-onnx does not expose ``ys_log_probs``.
    """
    words, cur = [], None
    for i, (tok, t) in enumerate(zip(tokens, timestamps)):
        lp = logprobs[i] if i < len(logprobs) else None
        if is_word_start(tok) or cur is None:
            if cur: words.append(cur)
            cur = {"text": strip_marker(tok), "start": offset_s + t, "end": None, "lp": [lp]}
        else:
            cur["text"] += tok
            cur["lp"].append(lp)
    if cur: words.append(cur)
    for a, b in zip(words, words[1:]):
        a["end"] = b["start"]
    if words: words[-1]["end"] = offset_s + seg_end_s
    for w in words:
        lps = [x for x in w.pop("lp") if x is not None]
        w["conf"] = float(sum(lps) / len(lps)) if lps else None  # mean log-prob; lower = worse
    return words


def transcribe_segments(rec, samples, segments, *, sample_rate: int = 16_000,
                        progress=None) -> list[dict]:
    """Decode every VAD segment in order and return one flat, indexed word list.

    Sequential by design: one recognizer per worker process, no parallel episodes
    (PLAN §3, CLAUDE.md rule 6).
    """
    from . import vad as vad_mod

    words: list[dict] = []
    for n, (start_s, end_s) in enumerate(segments):
        chunk = vad_mod.slice_samples(samples, start_s, end_s, sample_rate)
        if chunk.size == 0:
            continue
        res = transcribe_segment(rec, chunk, sample_rate)
        seg_words = tokens_to_words(
            res["tokens"], res["timestamps"], res["logprobs"],
            offset_s=start_s, seg_end_s=end_s - start_s,
        )
        words.extend(seg_words)
        if progress is not None:
            progress(n + 1, len(segments))
    for i, w in enumerate(words):
        w["i"] = i
    return words


def engine_block(params: AsrParams, *, hotwords_sha256: str | None = None) -> dict:
    """The ``engine`` block of the raw JSON (PLAN §5)."""
    try:
        import sherpa_onnx
        version = getattr(sherpa_onnx, "__version__", "unknown")
    except ImportError:  # pragma: no cover — only in test environments
        version = "unknown"
    return {
        "name": "zipformer-30m-rnnt-6000h",
        "hf_repo": "hynt/Zipformer-30M-RNNT-6000h",
        "files": params.model_files(),
        "sherpa_onnx_version": version,
        "params": params.as_json(hotwords_sha256=hotwords_sha256),
    }
