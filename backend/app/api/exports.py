"""Export endpoints (PLAN §9).

    GET /episodes/{id}/export.{json|verified.json|eaf|txt|csv|srt|docx}
    GET /exports/corpus.zip?tier=verified|all

Every response is regenerated from the raw JSON plus the verified layer (PLAN §0.2) —
nothing is cached to disk and then allowed to drift from the record it came from.

``docx`` is not in PLAN §1.5. It was added because the client's reference deliverable
(`resource/docs/*.docx`) is a Word document, and it is a *layout* only: speaker headings
plus one paragraph per utterance, with the text unchanged (CLAUDE.md rule 1).
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import loader
from ..db import get_session
from ..exports import TIER_ASR, TIER_VERIFIED, csv, docx, eaf, json_verified, srt, txt
from ..models import Episode
from .deps import require_editor

router = APIRouter(tags=["exports"])

#: format -> (media type, filename suffix)
FORMATS = {
    "json": ("application/json; charset=utf-8", "json"),
    "verified.json": ("application/json; charset=utf-8", "verified.json"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "verified.txt": ("text/plain; charset=utf-8", "verified.txt"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "srt": ("application/x-subrip; charset=utf-8", "srt"),
    "eaf": ("application/xml; charset=utf-8", "eaf"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
}


def _load(session: Session, episode_id: uuid.UUID):
    """``(episode, raw doc, speakers, overrides)`` for the current transcript."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="episode not found")
    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        raise HTTPException(status_code=409, detail="episode has no transcript yet")
    path = Path(transcript.raw_json_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"raw JSON missing: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    return (
        episode,
        doc,
        loader.speaker_labels(session, episode.id),
        loader.overrides_for(session, transcript.id),
    )


def render(fmt: str, doc: dict, speakers: dict, overrides: dict,
           title: str) -> bytes:
    """Render one format to bytes, applying the verified layer where the tier wants it."""
    verified_doc = json_verified.build(doc, overrides=overrides, speakers=speakers)

    if fmt == "json":
        return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if fmt == "verified.json":
        return json_verified.render(
            doc, overrides=overrides, speakers=speakers
        ).encode("utf-8")
    if fmt == "txt":
        return txt.render(doc, tier=TIER_ASR, speakers=speakers).encode("utf-8")
    if fmt == "verified.txt":
        return txt.render(
            verified_doc, tier=TIER_VERIFIED, speakers=speakers
        ).encode("utf-8")
    if fmt == "csv":
        return csv.render(doc, speakers=speakers).encode("utf-8")
    if fmt == "srt":
        return srt.render(
            verified_doc, tier=TIER_VERIFIED, speakers=speakers
        ).encode("utf-8")
    if fmt == "eaf":
        return eaf.render(
            verified_doc, tier=TIER_VERIFIED, speakers=speakers
        ).encode("utf-8")
    if fmt == "docx":
        return docx.render_bytes(
            verified_doc, tier=TIER_VERIFIED, speakers=speakers, title=title
        )
    raise HTTPException(status_code=404, detail=f"unknown format {fmt!r}")


@router.get("/episodes/{episode_id}/export.{fmt}")
def export_episode(
    episode_id: uuid.UUID,
    fmt: str,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> Response:
    if fmt not in FORMATS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}",
        )
    episode, doc, speakers, overrides = _load(session, episode_id)
    media_type, suffix = FORMATS[fmt]
    title = episode.title or episode.slug
    body = render(fmt, doc, speakers, overrides, title)
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition":
                f'attachment; filename="{episode.slug}.{suffix}"'
        },
    )


@router.get("/exports/corpus.zip")
def corpus_zip(
    tier: str = Query("verified", pattern="^(verified|all)$"),
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> StreamingResponse:
    """The whole corpus as one zip.

    ``tier=verified`` ships only episodes someone has actually verified; ``all`` ships
    every transcribed episode, engine output included. Built in memory because the
    corpus is text — the audio is deliberately not in here.
    """
    episodes = list(session.scalars(select(Episode).order_by(Episode.slug)))
    buf = io.BytesIO()
    included = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for episode in episodes:
            transcript = loader.current_transcript(session, episode.id)
            if transcript is None:
                continue
            path = Path(transcript.raw_json_path)
            if not path.exists():
                continue
            overrides = loader.overrides_for(session, transcript.id)
            n_verified = sum(
                1 for o in overrides.values() if o.get("text_verified") is not None
            )
            if tier == "verified" and not n_verified:
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            speakers = loader.speaker_labels(session, episode.id)
            title = episode.title or episode.slug
            for fmt in ("json", "verified.json", "txt", "csv", "srt", "eaf", "docx"):
                archive.writestr(
                    f"{episode.slug}/{episode.slug}.{FORMATS[fmt][1]}",
                    render(fmt, doc, speakers, overrides, title),
                )
            included += 1

        archive.writestr(
            "README.txt",
            "vn-stt-corpus export\n"
            f"tier: {tier}\n"
            f"episodes: {included}\n\n"
            "Verbatim corpus: fillers, repetitions and false starts are data, not "
            "errors (PLAN 0.1).\n"
            "ASR engine: hynt/Zipformer-30M-RNNT-6000h, CC BY-NC-ND 4.0 "
            "(non-commercial) - see LICENSE-NOTICE.md.\n",
        )

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="corpus-{tier}.zip"'},
    )
