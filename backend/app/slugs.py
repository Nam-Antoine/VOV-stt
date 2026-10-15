"""ASCII slugs for identifiers (episode slugs, project slugs) — never for content.

Shared by ``ingest.py`` (episodes) and ``api/projects.py`` (projects): both need the
same "strip diacritics, dashes, make unique" treatment for a different table/column.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session


def slugify(value: str, *, fallback: str = "item") -> str:
    """ASCII slug for filenames and URLs only.

    This strips diacritics, which would be a verbatim violation applied to transcript
    text (PLAN §0.1). It is applied to **identifiers**, never to anything a verifier
    reads as content — the real title/name is stored unchanged elsewhere.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or fallback


def unique_slug(session: Session, column, base: str) -> str:
    """``base``, or ``base-2``, ``base-3``… — unique against ``column`` (``Episode.slug``…)."""
    slug, n = base, 1
    while session.scalar(select(column).where(column == slug)) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug
