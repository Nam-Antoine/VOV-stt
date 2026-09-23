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
from .. import readable as readable_mod
from ..db import get_session
from ..exports import TIER_ASR, TIER_VERIFIED, csv, docx, eaf, json_verified, srt, txt
from ..exports import readable as readable_export
from ..models import Episode
from .deps import refresh_readable_layer, require_editor, require_punct_model

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
    # Reading copies: punctuation + capitals from the derived readable layer. Not corpus.
    "readable.txt": ("text/plain; charset=utf-8", "txt"),
    "readable.docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "readable.pdf": ("application/pdf", "pdf"),
}


def _load(session: Session, episode_id: uuid.UUID):
    """``(episode, raw doc, speakers, overrides)`` for the current transcript."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")
    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        raise HTTPException(status_code=409, detail="tập này chưa có bản chép lời")
    path = Path(transcript.raw_json_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"thiếu file JSON gốc: {path}")
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
    raise HTTPException(status_code=404, detail=f"định dạng không hỗ trợ {fmt!r}")


def _readable(session: Session, episode_id: uuid.UUID, fmt: str):
    """Refresh stale turns of the readable layer, then lay it out."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="không tìm thấy tập")
    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        raise HTTPException(status_code=409, detail="tập này chưa có bản chép lời")
    refresh_readable_layer(session, transcript)
    items = [
        {"speaker": u.speaker, "text": u.text_readable}
        for u in readable_mod.ordered_utterances(session, transcript.id)
    ]
    speakers = loader.speaker_labels(session, episode.id)
    title = episode.title or episode.slug
    if fmt == "readable.txt":
        return episode, readable_export.render_txt(
            items, speakers=speakers, title=title).encode("utf-8")
    if fmt == "readable.pdf":
        return episode, readable_export.render_pdf(items, speakers=speakers, title=title)
    return episode, readable_export.render_docx(items, speakers=speakers, title=title)


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
            detail=f"định dạng không hỗ trợ {fmt!r}; chỉ nhận: {', '.join(FORMATS)}",
        )
    media_type, suffix = FORMATS[fmt]
    if fmt.startswith("readable."):
        episode, body = _readable(session, episode_id, fmt)
    else:
        episode, doc, speakers, overrides = _load(session, episode_id)
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


@router.get("/exports/all.zip")
def all_readable_zip(
    fmt: str = Query("readable.docx", pattern=r"^readable\.(docx|pdf|txt)$"),
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> StreamingResponse:
    """Every finished episode's reading copy in one format, one file per episode.

    Episodes still being transcribed or waiting for speaker labels are skipped, and
    listed in the zip's README so nobody wonders where they went.
    """
    # Without the model every episode would fail; say so once, not once per file.
    require_punct_model()
    suffix = FORMATS[fmt][1]
    buf = io.BytesIO()
    skipped: list[str] = []
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for episode in session.scalars(select(Episode).order_by(Episode.slug)):
            try:
                _, body = _readable(session, episode.id, fmt)
            except HTTPException as exc:
                skipped.append(f"{episode.title or episode.slug}: {exc.detail}")
                continue
            name = episode.slug
            while f"{name}.{suffix}" in used:  # slugs are unique; guard anyway
                name += "_"
            used.add(f"{name}.{suffix}")
            archive.writestr(f"{name}.{suffix}", body)
        if skipped:
            archive.writestr(
                "CHUA-XONG.txt",
                "Các tập chưa có trong file này (chưa xử lý xong):\n\n"
                + "\n".join(skipped) + "\n",
            )
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="tat-ca-{suffix}.zip"'},
    )
