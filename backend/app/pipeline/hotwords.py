"""Contextual biasing terms → a hotwords file sherpa-onnx can load (PLAN §2, §11 T3).

This is our equivalent of ElevenLabs Scribe's "keyterms": proper nouns and show-specific
vocabulary that the acoustic model would otherwise mangle (*Thanh Huyền*, *Di Li*,
*quản chồng*, *giữ lửa*).

Two hard constraints:

* Hotwords only work with ``decoding_method="modified_beam_search"`` plus
  ``modeling_unit="bpe"`` and ``bpe_vocab=bpe.model`` (CLAUDE.md rule 5, PLAN §13).
  Greedy decoding ignores the file silently.
* A term is written **exactly as the operator typed it**. Do not casefold, strip
  diacritics, or reorder — the file is the operator's input, and the sha256 we record in
  the transcript row has to identify what was actually in force for that run.

The sha256 goes into ``transcripts.hotwords_sha256`` and the raw JSON's
``engine.params.hotwords_sha256`` so a transcript can always be traced back to the exact
bias list that produced it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HotwordsFile:
    path: Path | None
    sha256: str | None
    count: int

    @property
    def enabled(self) -> bool:
        return self.path is not None and self.count > 0


def render(terms: list[str]) -> str:
    """One term per line, in the order given, trailing newline.

    Blank lines are skipped because sherpa-onnx would treat one as an empty hotword;
    everything else is passed through verbatim, including internal spacing.
    """
    lines = [t for t in terms if t.strip()]
    return "".join(f"{t}\n" for t in lines)


def write(terms: list[str], path: Path) -> HotwordsFile:
    """Write the hotwords file and return its path, sha256 and term count."""
    path = Path(path)
    body = render(terms)
    if not body:
        return HotwordsFile(path=None, sha256=None, count=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return HotwordsFile(path=path, sha256=digest, count=len(body.splitlines()))


def unencodable(term: str, bpe_model: Path) -> list[str]:
    """Pieces of ``term`` the model's BPE cannot encode (empty list = usable).

    The vocabulary is UPPERCASE spoken form: ``Thanh Huyền`` encodes to
    ``▁T <unk> ▁H <unk>`` and biases nothing, silently. This only *reports* — the term
    is never rewritten here; the operator decides the spelling.
    """
    import sentencepiece as spm

    sp = _processor(str(bpe_model), spm)
    pieces = sp.encode(term, out_type=str)
    ids = sp.encode(term)
    words = term.split()
    if any(i == sp.unk_id() for i in ids):
        # Name the offending words, not BPE pieces: that is what the operator typed.
        return [w for w in words if sp.unk_id() in sp.encode(w)] or pieces
    return []


_PROCESSORS: dict[str, object] = {}


def _processor(path: str, spm):  # noqa: ANN001, ANN202 — sentencepiece module
    if path not in _PROCESSORS:
        _PROCESSORS[path] = spm.SentencePieceProcessor(model_file=path)
    return _PROCESSORS[path]


def read(path: Path) -> list[str]:
    """Read a hotwords file back, preserving order and spelling."""
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def active_terms(session) -> list[str]:  # noqa: ANN001 — SQLAlchemy Session
    """Active hotwords from the DB, newest weight first.

    TODO(T3): implement against ``app.models.Hotword`` once the DB layer lands —
    ``select(Hotword.term).where(Hotword.active.is_(True)).order_by(Hotword.weight.desc())``.
    Until then the pipeline takes terms from a file or the CLI.
    """
    raise NotImplementedError("T3: wire this to the hotwords table")
