"""Readable exports: punctuated, cased text for people to read.

    <TITLE>
    <paragraph>                 ← whole sentences, ~80 words or more
    <paragraph>

A paragraph never spans a pause longer than 1.5 s (:func:`app.pipeline.merge.passages`),
and ends at the first sentence end once it holds :data:`PARAGRAPH_WORDS` words. Radio
talk seldom pauses that long, so pauses alone would give a few pages-long paragraphs.
There are no speaker headings: the transcript has no speaker information.

These are **not** corpus exports. The text comes from the derived readable layer
(``utterances.text_readable``, see ``app/readable.py``), which adds punctuation and
capitals only; the verbatim corpus stays in ``json`` / ``verified.json`` / ``txt`` /
``csv`` / ``srt`` / ``eaf`` / ``docx``, which are unchanged (CLAUDE.md rule 1).

Input is a list of ``{"start": s, "end": s, "text": str}`` in playback order.
"""

from __future__ import annotations

import io
import zipfile

from ..pipeline.punctuate import sentences
from . import docx as _docx
from . import paragraphs

#: A paragraph ends at the first sentence end after this many words.
PARAGRAPH_WORDS = 80


def blocks(items: list[dict]) -> list[str]:
    """Paragraph texts: sentences of one passage, cut after ~PARAGRAPH_WORDS words."""
    out: list[str] = []
    for group in paragraphs(items):
        text = " ".join(t for t in ((it.get("text") or "").strip() for it in group) if t)
        cur: list[str] = []
        n = 0
        for sentence in sentences(text):
            cur.append(sentence)
            n += len(sentence.split())
            if n >= PARAGRAPH_WORDS:
                out.append(" ".join(cur))
                cur, n = [], 0
        if cur:
            out.append(" ".join(cur))
    return out


def render_txt(items: list[dict], *, title: str | None = None) -> str:
    lines: list[str] = []
    if title:
        lines += [title, ""]
    for text in blocks(items):
        lines += [text, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def build_document_xml(items: list[dict], *, title: str | None = None) -> str:
    parts: list[str] = []
    if title:
        parts.append(_docx._para(title, "DocTitle"))
    parts.extend(_docx._para(text) for text in blocks(items))
    body = "".join(parts) or _docx._para("")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_docx.W_NS}"><w:body>{body}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )


def render_docx(items: list[dict], *, title: str | None = None) -> bytes:
    name = title or "transcript"
    document_xml = build_document_xml(items, title=name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in (
            ("[Content_Types].xml", _docx._CONTENT_TYPES),
            ("_rels/.rels", _docx._ROOT_RELS),
            ("word/_rels/document.xml.rels", _docx._DOC_RELS),
            ("word/styles.xml", _docx._STYLES),
            ("docProps/core.xml", _docx._core_xml(name)),
            ("word/document.xml", document_xml),
        ):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data.encode("utf-8"))
    return buf.getvalue()


# DejaVu covers the full Vietnamese range; Times New Roman (the .docx font) isn't in the
# image. Installed by fonts-dejavu-core (backend/Dockerfile).
PDF_FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def render_pdf(items: list[dict], *, title: str | None = None) -> bytes:
    """Same layout as ``render_docx``: title, then one paragraph per passage, A4 with
    2 cm margins."""
    from fpdf import FPDF

    name = title or "transcript"
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_title(name)
    pdf.add_font("Serif", "", f"{PDF_FONT_DIR}/DejaVuSerif.ttf")
    pdf.add_font("Serif", "B", f"{PDF_FONT_DIR}/DejaVuSerif-Bold.ttf")
    pdf.add_page()
    width = pdf.epw

    pdf.set_font("Serif", "B", 16)
    pdf.multi_cell(width, 8, name, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Serif", "", 12)
    for text in blocks(items):
        pdf.multi_cell(width, 6.5, text, align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    return bytes(pdf.output())
