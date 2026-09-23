#!/usr/bin/env python3
"""Convert the hand-verified episode docx into ``pilot/reference.txt`` (PLAN §4.1).

Output is one utterance per line, ``SPEAKER<TAB>text`` — the shape ``run_pilot.py``
loads and the same shape ``app/exports/txt.py`` emits, so a hypothesis and the
reference can be diffed directly.

The docx marks speakers with a paragraph that is exactly ``Label:``. Two lines in the
source look like that but are mid-sentence colons, so a heading is only accepted when it
also matches a known speaker pattern — otherwise a sentence like ``Nghĩa là:`` would
silently swallow the following ten paragraphs into a phantom speaker.

**This script does not clean text.** It extracts what the docx says, verbatim, including
its punctuation and casing. ``run_pilot.py`` lowercases and strips punctuation from the
reference at scoring time only (PLAN §4.2); the file on disk keeps the original.

Usage
-----
    python scripts/docx_to_reference.py \
        --docx "resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx" \
        --out pilot/reference.txt
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: A paragraph of the form "Label:" is a speaker heading only if the label looks like
#: one of these. Keeps mid-speech colons ("Nghĩa là:") from becoming speakers.
SPEAKER_PATTERNS = (
    re.compile(r"^MC\b", re.IGNORECASE),
    re.compile(r"^Nhà văn\b", re.IGNORECASE),
    re.compile(r"^Ý kiến\b", re.IGNORECASE),
    re.compile(r"^Nhân vật\b", re.IGNORECASE),
    re.compile(r"^(Khách mời|Phóng viên|Biên tập viên)\b", re.IGNORECASE),
)

HEADING = re.compile(r"^([^:]{1,40}):$")

#: PLAN §4.2 filler set, split by what the tokens actually are in Vietnamese.
HESITATION = ("à", "ừ", "ờ", "ừm")
GRAMMATICAL = ("thì", "là", "ấy", "nhé", "đấy")


def paragraphs(docx: Path) -> list[str]:
    """Every non-empty paragraph, text only, in document order."""
    with zipfile.ZipFile(docx) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for para in root.iter(f"{W}p"):
        text = "".join(t.text or "" for t in para.iter(f"{W}t")).strip()
        if text:
            out.append(text)
    return out


def is_speaker_heading(text: str) -> str | None:
    m = HEADING.match(text)
    if not m:
        return None
    label = m.group(1).strip()
    return label if any(p.match(label) for p in SPEAKER_PATTERNS) else None


def to_rows(paras: list[str]) -> list[tuple[str, str]]:
    """``[(speaker, text), …]``. Paragraphs before the first heading are dropped."""
    rows, current = [], None
    for text in paras:
        label = is_speaker_heading(text)
        if label:
            current = label
        elif current:
            rows.append((current, text))
    return rows


def normalise_for_count(text: str) -> list[str]:
    """Lowercase + strip punctuation — for *counting only*, never for output."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def audit(rows: list[tuple[str, str]]) -> dict:
    """Is this reference actually verbatim? PLAN §4.2 depends on the answer."""
    text = " ".join(t for _, t in rows)
    tokens = normalise_for_count(text)
    counts = {f: tokens.count(f) for f in HESITATION + GRAMMATICAL}
    return {
        "lines": len(rows),
        "tokens": len(tokens),
        "speakers": Counter(s for s, _ in rows),
        "counts": counts,
        "hesitation_total": sum(counts[f] for f in HESITATION),
        "grammatical_total": sum(counts[f] for f in GRAMMATICAL),
        "punctuation": len(re.findall(r"[.,!?;:\"']", text)),
        "capitalised": sum(1 for w in text.split() if w[:1].isupper()),
    }


def report(a: dict) -> str:
    per_1k = 1000 * a["hesitation_total"] / a["tokens"] if a["tokens"] else 0.0
    lines = [
        f"{a['lines']} lines, {a['tokens']} tokens, {len(a['speakers'])} speakers",
        "",
        "speakers:",
        *[f"  {s:<22} {n:>4} lines" for s, n in a["speakers"].most_common()],
        "",
        "PLAN §4.2 filler set, counted in the reference:",
        *[f"  {f:<5} {a['counts'][f]:>5}   hesitation marker" for f in HESITATION],
        *[f"  {f:<5} {a['counts'][f]:>5}   ordinary grammatical word" for f in GRAMMATICAL],
        "",
        f"  hesitation markers : {a['hesitation_total']:>5}  "
        f"({per_1k:.1f} per 1000 tokens)",
        f"  grammatical words  : {a['grammatical_total']:>5}",
        f"  punctuation marks  : {a['punctuation']:>5}",
        f"  capitalised words  : {a['capitalised']:>5}",
    ]
    if per_1k < 5.0:
        lines += [
            "",
            "  *** WARNING: this reference is not verbatim. ***",
            "  A spontaneous radio conversation carries far more hesitation markers",
            "  than this. Combined with the punctuation and casing counts, the docx",
            "  has been edited into readable prose.",
            "",
            "  Consequences for the T2 gate (PLAN §4.2):",
            "   - filler recall = fillers_in_hyp / fillers_in_ref. With a near-zero",
            "     denominator for à/ừ/ờ/ừm, the pooled figure is decided almost",
            "     entirely by 'thì' and 'là' — ordinary words any ASR emits freely —",
            "     so it can read >0.85 while every real filler is being dropped.",
            "   - worse, fillers the engine *does* keep count as insertions against",
            "     this reference and inflate WER, penalising the wanted behaviour.",
            "",
            "  Escalate before running the sweep. See PLAN §13, last row.",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docx", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("pilot/reference.txt"))
    ap.add_argument("--audit-only", action="store_true",
                    help="print the verbatim audit and write nothing")
    args = ap.parse_args(argv)

    if not args.docx.exists():
        print(f"error: {args.docx} not found", file=sys.stderr)
        return 1

    rows = to_rows(paragraphs(args.docx))
    if not rows:
        print("error: no speaker headings found — check SPEAKER_PATTERNS",
              file=sys.stderr)
        return 1

    a = audit(rows)
    print(report(a))

    if args.audit_only:
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for speaker, text in rows:
            # Tabs inside the text would break the two-column format.
            fh.write(f"{speaker}\t{text.replace(chr(9), ' ')}\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
