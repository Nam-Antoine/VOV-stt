"""Readable exports: punctuated, cased text laid out like the client's reference.

Reference: ``resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx`` —

    <TITLE>
    <speaker label>:            ← bold, own paragraph
    <one sentence per paragraph>
    <one sentence per paragraph>
                                ← blank line between turns
    <next speaker>:
    ...

These are **not** corpus exports. The text comes from the derived readable layer
(``utterances.text_readable``, see ``app/readable.py``), which adds punctuation and
capitals only; the verbatim corpus stays in ``json`` / ``verified.json`` / ``txt`` /
``csv`` / ``srt`` / ``eaf`` / ``docx``, which are unchanged (CLAUDE.md rule 1).

Input is a list of ``{"speaker": int, "text": str}`` in playback order.
"""

from __future__ import annotations

import io
import zipfile

from ..pipeline.punctuate import sentences
from . import docx as _docx
from . import speaker_label


def blocks(items: list[dict], speakers: dict | None) -> list[tuple[str, list[str]]]:
    """``[(speaker label, [sentence, ...]), ...]`` with consecutive speakers merged."""
    out: list[tuple[str, list[str]]] = []
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        label = speaker_label(speakers, it.get("speaker"))
        if out and out[-1][0] == label:
            # Sentences can run across utterance boundaries: re-split the joined turn.
            out[-1] = (label, sentences(" ".join(out[-1][1] + [text])))
        else:
            out.append((label, sentences(text)))
    return out


def render_txt(items: list[dict], *, speakers: dict | None = None,
               title: str | None = None) -> str:
    lines: list[str] = []
    if title:
        lines += [title, ""]
    for label, sents in blocks(items, speakers):
        lines.append(f"{label}:")
        lines.extend(sents)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_document_xml(items: list[dict], *, speakers: dict | None = None,
                       title: str | None = None) -> str:
    parts: list[str] = []
    if title:
        parts.append(_docx._para(title, "DocTitle"))
    for label, sents in blocks(items, speakers):
        parts.append(_docx._para(f"{label}:", "Speaker"))
        parts.extend(_docx._para(s) for s in sents)
    body = "".join(parts) or _docx._para("")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_docx.W_NS}"><w:body>{body}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )


def render_docx(items: list[dict], *, speakers: dict | None = None,
                title: str | None = None) -> bytes:
    name = title or "transcript"
    document_xml = build_document_xml(items, speakers=speakers, title=name)
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


def render_pdf(items: list[dict], *, speakers: dict | None = None,
               title: str | None = None) -> bytes:
    """Same layout as ``render_docx``: title, bold ``speaker:`` heading, one sentence
    per line, A4 with 2 cm margins."""
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
    for label, sents in blocks(items, speakers):
        pdf.ln(3)
        # Keep a heading with its first sentence rather than stranding it at a page foot.
        if pdf.will_page_break(14):
            pdf.add_page()
        pdf.set_font("Serif", "B", 12)
        pdf.multi_cell(width, 6.5, f"{label}:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Serif", "", 12)
        for s in sents:
            pdf.multi_cell(width, 6.5, s, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
    return bytes(pdf.output())
