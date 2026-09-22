"""Word (.docx) export, laid out like the client's hand-verified reference.

The reference document (``resource/docs/TÂM SỰ CHIẾN THUẬT QUẢN TRỊ CHỒNG.docx``) is
organised as:

    <speaker label>:          ← its own paragraph, bold
    <utterance>               ← one paragraph per utterance
    <utterance>
    <next speaker>:
    ...

so that is what this renders. Consecutive utterances from the same speaker sit under one
heading, which is what makes the document readable — and is purely a *grouping* of
paragraphs, not an edit: no utterance text is joined, split, re-cased or punctuated
(PLAN §0.1, CLAUDE.md rule 1).

Written as raw OOXML into a zip by hand. python-docx would be a new runtime dependency
for one file format, and the subset of WordprocessingML a transcript needs is small and
stable. ``scripts/docx_to_reference.py`` already reads this same format, so the two are
symmetric.
"""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import TIER_ASR, speaker_label, utterance_text

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>
"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>
"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

# Times New Roman 13pt (sz is half-points) matches the reference document's body text.
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>
      <w:sz w:val="26"/><w:szCs w:val="26"/>
    </w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Speaker">
    <w:name w:val="Speaker"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="60"/><w:keepNext/></w:pPr>
    <w:rPr><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DocTitle">
    <w:name w:val="DocTitle"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="240"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr>
  </w:style>
</w:styles>
"""


def _para(text: str, style: str | None = None) -> str:
    """One ``<w:p>``. ``xml:space="preserve"`` so leading/trailing spaces survive."""
    pr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return (
        f"<w:p>{pr}<w:r><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"
    )


def build_document_xml(doc: dict, *, tier: str = TIER_ASR,
                       speakers: dict | None = None,
                       title: str | None = None) -> str:
    """The ``word/document.xml`` body: a title, then speaker-grouped utterances."""
    parts: list[str] = []
    if title:
        parts.append(_para(title, "DocTitle"))

    last_label: str | None = None
    for u in doc.get("utterances", []):
        label = speaker_label(speakers, u.get("speaker"))
        if label != last_label:
            parts.append(_para(f"{label}:", "Speaker"))
            last_label = label
        # Verbatim: the utterance goes in as one run, unchanged.
        parts.append(_para(utterance_text(u, tier)))

    body = "".join(parts) or _para("")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{body}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )


def _core_xml(title: str) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title>"
        "<dc:creator>vn-stt-corpus</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def render_bytes(doc: dict, *, tier: str = TIER_ASR, speakers: dict | None = None,
                 title: str | None = None) -> bytes:
    """The whole .docx as bytes."""
    name = title or (doc.get("source") or {}).get("filename") or "transcript"
    document_xml = build_document_xml(doc, tier=tier, speakers=speakers, title=name)

    import io

    buf = io.BytesIO()
    # Deterministic timestamps: two exports of an unchanged transcript compare equal.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _ROOT_RELS),
            ("word/_rels/document.xml.rels", _DOC_RELS),
            ("word/styles.xml", _STYLES),
            ("docProps/core.xml", _core_xml(name)),
            ("word/document.xml", document_xml),
        ):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data.encode("utf-8"))
    return buf.getvalue()


def write(doc: dict, path, *, tier: str = TIER_ASR, speakers: dict | None = None,
          title: str | None = None) -> None:
    Path(path).write_bytes(render_bytes(doc, tier=tier, speakers=speakers, title=title))
