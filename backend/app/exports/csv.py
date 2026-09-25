"""Word-level CSV export (PLAN §1.5) — one row per word.

Columns: ``i, start_s, end_s, conf, text``.

Written with the stdlib ``csv`` writer so a word containing a comma or a quote is
escaped rather than mangled. ``QUOTE_MINIMAL`` keeps the common case readable.
"""

from __future__ import annotations

import csv as _csv
import io

COLUMNS = ["i", "start_s", "end_s", "conf", "text"]


def render(doc: dict) -> str:
    """Return the CSV as a string with ``\\n`` line endings."""
    buf = io.StringIO(newline="")
    writer = _csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for w in doc.get("words", []):
        writer.writerow([
            w.get("i"),
            w.get("start"),
            w.get("end"),
            w.get("conf"),
            w.get("text", ""),   # verbatim
        ])
    return buf.getvalue()


def write(doc: dict, path) -> None:
    from pathlib import Path

    Path(path).write_text(render(doc), encoding="utf-8")
