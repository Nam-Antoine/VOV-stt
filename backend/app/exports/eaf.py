"""ELAN (.eaf) export — ELAN Annotation Format 3.0 (PLAN §1.5, §11 T3).

One tier per speaker label, one annotation per utterance, with shared time slots so ELAN
can click-to-play against the episode's 16 kHz WAV.

EAF structure, briefly:

    ANNOTATION_DOCUMENT
      HEADER          media descriptor + ms time units
      TIME_ORDER      TIME_SLOT id -> TIME_VALUE in **milliseconds**
      TIER *          one per speaker; ALIGNABLE_ANNOTATION referencing two slots
      LINGUISTIC_TYPE the tiers' type ("utterance", time-alignable)

Text goes into ANNOTATION_VALUE exactly as it is. XML escaping of ``&``/``<`` is
encoding, not normalisation — the parsed value round-trips identically, which is what
``test_eaf_roundtrip`` and ``test_no_normalisation`` check.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from . import TIER_ASR, speaker_label, utterance_text

EAF_VERSION = "3.0"
LINGUISTIC_TYPE = "utterance"


def _header(root: ET.Element, doc: dict, media_url: str | None) -> None:
    header = ET.SubElement(
        root, "HEADER", {"MEDIA_FILE": "", "TIME_UNITS": "milliseconds"}
    )
    audio = doc.get("audio") or {}
    source = doc.get("source") or {}
    url = media_url or source.get("filename") or ""
    ET.SubElement(
        header, "MEDIA_DESCRIPTOR",
        {
            "MEDIA_URL": url,
            "RELATIVE_MEDIA_URL": f"./{Path(url).name}" if url else "",
            "MIME_TYPE": "audio/x-wav",
        },
    )
    for key, value in (
        ("schema_version", doc.get("schema_version")),
        ("episode_id", doc.get("episode_id")),
        ("engine", (doc.get("engine") or {}).get("name")),
        ("duration_s", audio.get("duration_s")),
        ("source_sha256", source.get("sha256")),
    ):
        if value is not None:
            ET.SubElement(header, "PROPERTY", {"NAME": key}).text = str(value)


def _ms(seconds) -> int:
    return int(round(float(seconds or 0.0) * 1000))


def build(doc: dict, *, tier: str = TIER_ASR, speakers: dict | None = None,
          media_url: str | None = None, author: str = "vn-stt-corpus") -> ET.ElementTree:
    """Build the EAF document tree."""
    root = ET.Element(
        "ANNOTATION_DOCUMENT",
        {
            "AUTHOR": author,
            "DATE": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "FORMAT": EAF_VERSION,
            "VERSION": EAF_VERSION,
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://www.mpi.nl/tools/elan/EAFv3.0.xsd",
        },
    )
    _header(root, doc, media_url)

    utterances = doc.get("utterances", [])
    time_order = ET.SubElement(root, "TIME_ORDER")
    # Two slots per utterance, in document order, so ELAN sees a valid TIME_ORDER.
    slots: list[tuple[str, int]] = []
    bounds: list[tuple[str, str]] = []
    for n, u in enumerate(utterances):
        start_id, end_id = f"ts{2 * n + 1}", f"ts{2 * n + 2}"
        slots.append((start_id, _ms(u.get("start"))))
        slots.append((end_id, _ms(u.get("end"))))
        bounds.append((start_id, end_id))
    for slot_id, value in slots:
        ET.SubElement(time_order, "TIME_SLOT",
                      {"TIME_SLOT_ID": slot_id, "TIME_VALUE": str(value)})

    # Group utterances by speaker label: one ELAN tier per label.
    by_tier: dict[str, list[tuple[int, dict]]] = {}
    for n, u in enumerate(utterances):
        by_tier.setdefault(speaker_label(speakers, u.get("speaker")), []).append((n, u))

    annotation_id = 0
    for tier_name, rows in by_tier.items():
        tier_el = ET.SubElement(
            root, "TIER",
            {
                "LINGUISTIC_TYPE_REF": LINGUISTIC_TYPE,
                "TIER_ID": tier_name,
                "PARTICIPANT": tier_name,
            },
        )
        for n, u in rows:
            annotation_id += 1
            ann = ET.SubElement(tier_el, "ANNOTATION")
            start_id, end_id = bounds[n]
            alignable = ET.SubElement(
                ann, "ALIGNABLE_ANNOTATION",
                {
                    "ANNOTATION_ID": f"a{annotation_id}",
                    "TIME_SLOT_REF1": start_id,
                    "TIME_SLOT_REF2": end_id,
                },
            )
            # Verbatim. ElementTree escapes &, < and > on write and unescapes on read.
            ET.SubElement(alignable, "ANNOTATION_VALUE").text = utterance_text(u, tier)

    ET.SubElement(
        root, "LINGUISTIC_TYPE",
        {
            "GRAPHIC_REFERENCES": "false",
            "LINGUISTIC_TYPE_ID": LINGUISTIC_TYPE,
            "TIME_ALIGNABLE": "true",
        },
    )
    return ET.ElementTree(root)


def render(doc: dict, *, tier: str = TIER_ASR, speakers: dict | None = None,
           media_url: str | None = None) -> str:
    """Return the EAF as a UTF-8 XML string."""
    tree = build(doc, tier=tier, speakers=speakers, media_url=media_url)
    ET.indent(tree, space="    ")
    return ET.tostring(tree.getroot(), encoding="unicode", xml_declaration=True) + "\n"


def write(doc: dict, path, *, tier: str = TIER_ASR, speakers: dict | None = None,
          media_url: str | None = None) -> None:
    Path(path).write_text(
        render(doc, tier=tier, speakers=speakers, media_url=media_url), encoding="utf-8"
    )
