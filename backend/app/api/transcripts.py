"""Transcript reads: the editor payload, the raw JSON, and audio streaming (PLAN §9)."""

from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import player
from .. import readable as readable_mod
from ..config import settings
from ..db import get_session
from ..models import Episode, Speaker, Transcript, Utterance, Word
from ..schemas import SpeakerOut, TranscriptOut, UtteranceOut, WordOut
from .deps import refresh_readable_layer, require_editor

router = APIRouter(prefix="/transcripts", tags=["transcripts"])

#: Bytes served per range request. Big enough that seeking is not chatty, small enough
#: that a seek does not pull a whole 28 MB WAV before the first sample plays.
RANGE_CHUNK = 1 << 20

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _transcript_or_404(session: Session, transcript_id: uuid.UUID) -> Transcript:
    transcript = session.get(Transcript, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="không tìm thấy bản chép lời")
    return transcript


@router.get("/{transcript_id}", response_model=TranscriptOut)
def get_transcript(
    transcript_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> TranscriptOut:
    """Words + utterances + speakers — what the editor loads in one request.

    A 15-minute episode is a few thousand words. They go in one payload rather than
    being paginated, so click-to-play never has a gap to load across.
    """
    transcript = _transcript_or_404(session, transcript_id)

    words = [
        WordOut(i=w.i, text=w.text, start_s=float(w.start_s),
                end_s=None if w.end_s is None else float(w.end_s),
                conf=None if w.conf is None else float(w.conf), speaker=w.speaker)
        for w in session.scalars(
            select(Word).where(Word.transcript_id == transcript.id).order_by(Word.i)
        )
    ]
    utterances = [
        UtteranceOut.model_validate(u).model_copy(
            update={"text_readable": None if readable_mod.is_stale(u) else u.text_readable}
        )
        for u in session.scalars(
            select(Utterance)
            .where(Utterance.transcript_id == transcript.id)
            .order_by(Utterance.i)
        )
    ]
    speakers = [
        SpeakerOut(cluster=int(c), label=label)
        for c, label in session.execute(
            select(Speaker.cluster, Speaker.label)
            .where(Speaker.episode_id == transcript.episode_id)
            .order_by(Speaker.cluster)
        ).all()
    ]
    return TranscriptOut(
        id=transcript.id,
        episode_id=transcript.episode_id,
        engine=transcript.engine,
        engine_version=transcript.engine_version,
        params=transcript.params,
        hotwords_sha256=transcript.hotwords_sha256,
        created_at=transcript.created_at,
        speakers_pending=transcript.speakers_pending,
        readable_available=settings.punct_available(),
        words=words,
        utterances=utterances,
        speakers=speakers,
    )


@router.post("/{transcript_id}/readable")
def refresh_readable(
    transcript_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> dict:
    """Bring the punctuated reading layer up to date with the current text.

    Only turns that changed since the last run are recomputed, so after one edit this
    takes well under a second; a transcript that never had the layer takes ~20 s.
    The corpus text is not touched (CLAUDE.md rule 1).
    """
    transcript = _transcript_or_404(session, transcript_id)
    return {"written": refresh_readable_layer(session, transcript)}


@router.get("/{transcript_id}/raw")
def get_raw_json(
    transcript_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> FileResponse:
    """The immutable raw JSON file, served straight off disk (PLAN §0.2)."""
    transcript = _transcript_or_404(session, transcript_id)
    path = Path(transcript.raw_json_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"thiếu file JSON gốc: {path}")
    return FileResponse(
        path,
        media_type="application/json; charset=utf-8",
        filename=path.name,
    )


def _audio_path(session: Session, transcript: Transcript) -> Path:
    """The 16 kHz WAV if the pipeline kept one, else the original upload.

    Timestamps are measured against the 16 kHz WAV (PLAN §13), so that is what the
    player should seek in whenever it exists.
    """
    episode = session.get(Episode, transcript.episode_id)
    if episode is None or not episode.audio_path:
        raise HTTPException(status_code=404, detail="thiếu file âm thanh của tập")
    original = Path(episode.audio_path)
    wav = original.with_suffix("").with_suffix(".16k.wav")
    candidate = original.parent / f"{original.stem}.16k.wav"
    for path in (candidate, wav, original):
        if path.exists():
            return path
    raise HTTPException(status_code=404, detail=f"thiếu file âm thanh: {original}")


@router.get("/{transcript_id}/audio")
def stream_audio(
    transcript_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> Response:
    """Range-request streaming. wavesurfer and click-to-play both need seeking."""
    transcript = _transcript_or_404(session, transcript_id)
    path = _audio_path(session, transcript)
    # The compressed listening copy once it exists (~5 MB vs ~27 MB); the WAV until then.
    if path.suffix == ".wav":
        path = player.proxy_or_schedule(path) or path
    size = path.stat().st_size
    media_type = {".wav": "audio/wav", ".m4a": "audio/mp4"}.get(path.suffix) or (
        mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}

    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=media_type, headers=headers)

    match = RANGE_RE.fullmatch(range_header.strip())
    if not match:
        raise HTTPException(status_code=416, detail="header Range không hợp lệ")
    raw_start, raw_end = match.groups()
    if raw_start:
        start = int(raw_start)
        end = int(raw_end) if raw_end else min(start + RANGE_CHUNK - 1, size - 1)
    else:
        # "bytes=-N" means the last N bytes.
        length = int(raw_end or 0)
        start = max(0, size - length)
        end = size - 1
    if start >= size:
        raise HTTPException(status_code=416, detail="vùng yêu cầu vượt quá cuối file")
    end = min(end, size - 1)

    def body():
        remaining = end - start + 1
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining > 0:
                chunk = fh.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        body(),
        status_code=206,
        media_type=media_type,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )


@router.get("/{transcript_id}/peaks")
def get_peaks(
    transcript_id: uuid.UUID,
    session: Session = Depends(get_session),
    editor: str = Depends(require_editor),
) -> Response:
    """Waveform peaks + exact duration, so the player never decodes the audio itself.

    404 when only the original upload exists (no 16 kHz WAV): the player then falls
    back to decoding in the browser, as before.
    """
    transcript = _transcript_or_404(session, transcript_id)
    path = _audio_path(session, transcript)
    if path.suffix != ".wav":
        raise HTTPException(status_code=404, detail="chưa có file WAV 16 kHz để vẽ dạng sóng")
    player.proxy_or_schedule(path)  # warm the listening copy while we are here
    return Response(
        content=json.dumps(player.peaks_for(path)),
        media_type="application/json",
        headers={"Cache-Control": "private, max-age=86400"},
    )
