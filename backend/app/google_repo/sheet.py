"""The index Sheet: one row per episode, Title linking to its Doc (Task 6).

Rebuilt from the database in full on every sync, and only written when a row changed.
No Guest column and no MC column: there is no speaker information.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import loader
from ..config import settings
from ..models import Episode, EpisodeGoogleDoc, Utterance
from . import state
from .client import Google, call
from .docs import doc_url, ensure_folder

log = logging.getLogger("google_repo")

SHEET_MIME = "application/vnd.google-apps.spreadsheet"

HEADER = [
    "Mã tập", "Tên tập (mở bản chép lời)", "Ngày phát", "Thời lượng", "Link gốc (audio)",
    "Trạng thái", "Người duyệt", "Số âm tiết",
]

#: Same wording as the web app (web/src/labels.ts).
STATUS_LABEL = {
    "ingested": "Đã tải lên", "queued": "Đang chờ", "processing": "Đang xử lý",
    "transcribed": "Đã chép lời", "verifying": "Đang duyệt", "verified": "Đã duyệt",
    "failed": "Lỗi",
}


def ensure_sheet(session: Session, g: Google) -> str:
    """The index Sheet's ID, creating it in the folder (header row frozen) on first use."""
    sheet_id = state.get(session, state.SHEET_ID)
    if sheet_id:
        return sheet_id
    folder_id = ensure_folder(session, g)
    sheet_id = call(g, g.drive.files().create(
        body={"name": settings.google_sheet_name, "mimeType": SHEET_MIME,
              "parents": [folder_id]},
        fields="id",
    ))["id"]
    state.put(session, state.SHEET_ID, sheet_id)
    tabs = call(g, g.sheets.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets.properties.sheetId"))["sheets"]
    call(g, g.sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": [{
        # Pinned, because formula argument separators depend on it: title_cell writes
        # ";" as vi_VN expects, and a "," there shows #ERROR!.
        "updateSpreadsheetProperties": {
            "properties": {"locale": "vi_VN"}, "fields": "locale",
        },
    }, {
        "updateSheetProperties": {
            "properties": {"sheetId": tabs[0]["properties"]["sheetId"],
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        },
    }]}))
    log.info("google: created sheet %r", settings.google_sheet_name)
    return sheet_id


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


def duration_text(seconds) -> str:  # noqa: ANN001 — Decimal or float
    if not seconds:
        return ""
    s = int(round(float(seconds)))
    return f"'{s // 60}:{s % 60:02d}"


def title_cell(title: str, doc_id: str | None) -> str:
    if not doc_id:
        return title
    return f'=HYPERLINK("{doc_url(doc_id)}"; "{title.replace(chr(34), chr(34) * 2)}")'


def rows(session: Session) -> list[list]:
    """Every episode, oldest air date first, in :data:`HEADER` order."""
    docs = {
        d.episode_id: d
        for d in session.scalars(
            select(EpisodeGoogleDoc).where(EpisodeGoogleDoc.episode_id.is_not(None)))
    }
    out: list[list] = []
    episodes = session.scalars(
        select(Episode).order_by(Episode.air_date.asc().nulls_last(), Episode.slug)
    )
    for ep in episodes:
        doc = docs.get(ep.id)
        verified_by = ""
        transcript = loader.current_transcript(session, ep.id)
        if transcript is not None:
            q = select(Utterance).where(Utterance.transcript_id == transcript.id,
                                        Utterance.text_verified.is_not(None))
            names = sorted({u.verified_by for u in session.scalars(q) if u.verified_by})
            verified_by = ", ".join(names)
        out.append([
            ep.slug,
            title_cell(ep.title or ep.slug, doc.doc_id if doc else None),
            ep.air_date.isoformat() if ep.air_date else "",
            duration_text(ep.duration_s),
            ep.source_url or "",
            STATUS_LABEL.get(ep.status, ep.status),
            verified_by,
            doc.syllables if doc and doc.doc_id and doc.syllables is not None else "",
        ])
    return out


def rebuild_sheet(session: Session, g: Google) -> bool:
    """Rewrite the Sheet from the DB. Returns False (no write) when nothing changed.

    A Sheet deleted in Drive (404) is recreated once.
    """
    from googleapiclient.errors import HttpError

    from .client import status_of

    try:
        return _rebuild(session, g)
    except HttpError as exc:
        if status_of(exc) != 404:
            raise
        log.warning("google: the index Sheet is gone (deleted in Drive?); recreating it")
        state.put(session, state.SHEET_ID, None)
        state.put(session, state.SHEET_SHA256, None)
        return _rebuild(session, g)


def _rebuild(session: Session, g: Google) -> bool:
    sheet_id = ensure_sheet(session, g)
    values = [HEADER, *rows(session)]
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    if state.get(session, state.SHEET_SHA256) == digest:
        return False
    call(g, g.sheets.spreadsheets().values().clear(spreadsheetId=sheet_id, range="A:Z",
                                                   body={}))
    call(g, g.sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id, range="A1", valueInputOption="USER_ENTERED",
        body={"values": values},
    ))
    state.put(session, state.SHEET_SHA256, digest)
    log.info("google: sheet rebuilt, %d rows", len(values) - 1)
    return True
