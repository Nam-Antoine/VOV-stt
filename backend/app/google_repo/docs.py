"""One Google Doc per transcribed episode, inside the repository folder (Task 5).

The Doc body is :func:`app.exports.plain.render_plain` with labels off — the same text
path as the other exports, so the verbatim gate covers it. The Doc is overwritten
whenever that text changes and never read back; edits belong in the app.

Nothing here deletes a file in Drive. A Doc someone deleted (404) is recreated.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import loader
from ..config import settings
from ..exports.plain import render_plain
from ..models import Episode, EpisodeGoogleDoc, Project
from .client import Google, call, short_error, status_of

log = logging.getLogger("google_repo")

FOLDER_MIME = "application/vnd.google-apps.folder"


def folder_name(project: Project) -> str:
    return f"{project.name} Corpus"


def share_editors(g: Google, folder_id: str) -> None:
    """Grant Editor to every address in ``GOOGLE_SHARE_EDITORS`` (project memory:
    the corpus owner must always be Editor on the corpus folder).

    Best-effort: one bad address must not stop the sync, so a failure here is logged
    and swallowed rather than raised.
    """
    for email in settings.google_share_editors:
        try:
            g.throttle()
            call(g, g.drive.permissions().create(
                fileId=folder_id, sendNotificationEmail=True,
                body={"type": "user", "role": "writer", "emailAddress": email},
                fields="id",
            ))
        except Exception as exc:  # noqa: BLE001 — sharing must not break the sync
            log.warning("google: could not share folder with %s: %s", email,
                        short_error(exc))


def ensure_folder(session: Session, g: Google, project: Project) -> str:
    """This project's Drive folder ID: created (and shared) once, renamed on demand.

    A rename also renames the index Sheet (a Drive file too, same ``files().update``)
    so both always carry the project's current name — one flag (``google_title``)
    tracks both, since they change together.
    """
    if project.google_folder_id:
        if project.google_title != project.name:
            g.throttle()
            call(g, g.drive.files().update(fileId=project.google_folder_id,
                                           body={"name": folder_name(project)},
                                           fields="id"))
            if project.google_sheet_id:
                # Duplicated format string: sheet.sheet_name() — kept local to avoid a
                # docs.py <-> sheet.py import cycle (sheet.py already imports docs.py).
                g.throttle()
                call(g, g.drive.files().update(
                    fileId=project.google_sheet_id,
                    body={"name": f"{project.name} Corpus — Index"}, fields="id"))
            project.google_title = project.name
            session.flush()
        return project.google_folder_id
    g.throttle()
    folder_id = call(g, g.drive.files().create(
        body={"name": folder_name(project), "mimeType": FOLDER_MIME},
        fields="id",
    ))["id"]
    project.google_folder_id = folder_id
    project.google_title = project.name
    session.flush()
    log.info("google: created folder %r for project %r", folder_name(project), project.slug)
    share_editors(g, folder_id)
    return folder_id


def doc_title(episode: Episode) -> str:
    return f"{episode.slug} — {episode.title or episode.slug}"


def doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


def _row(session: Session, episode: Episode) -> EpisodeGoogleDoc:
    row = session.scalar(
        select(EpisodeGoogleDoc).where(EpisodeGoogleDoc.episode_id == episode.id)
    )
    if row is None:
        row = EpisodeGoogleDoc(episode_id=episode.id)
        session.add(row)
    return row


def _end_index(g: Google, doc_id: str) -> int:
    doc = call(g, g.docs.documents().get(documentId=doc_id,
                                         fields="body(content(endIndex))"))
    content = (doc.get("body") or {}).get("content") or []
    return max((int(c.get("endIndex") or 0) for c in content), default=1)


def _move_into(g: Google, doc_id: str, folder_id: str) -> None:
    parents = call(g, g.drive.files().get(fileId=doc_id, fields="parents")).get("parents")
    if folder_id in (parents or []):
        return
    g.throttle()
    call(g, g.drive.files().update(fileId=doc_id, addParents=folder_id,
                                   removeParents=",".join(parents or []), fields="id"))


def _create(g: Google, row: EpisodeGoogleDoc, folder_id: str, title: str,
            text: str) -> None:
    g.throttle()
    # Recorded at once, so a failure below leaves a Doc the next sync finishes, not an
    # untracked one in the owner's Drive root.
    row.doc_id = call(g, g.docs.documents().create(body={"title": title}))["documentId"]
    _move_into(g, row.doc_id, folder_id)
    g.throttle()
    call(g, g.docs.documents().batchUpdate(documentId=row.doc_id, body={"requests": [
        {"insertText": {"location": {"index": 1}, "text": text}},
    ]}))


def _replace_text(g: Google, doc_id: str, text: str) -> None:
    end = _end_index(g, doc_id)
    requests: list[dict] = []
    if end > 2:
        requests.append({"deleteContentRange": {"range": {"startIndex": 1,
                                                          "endIndex": end - 1}}})
    requests.append({"insertText": {"location": {"index": 1}, "text": text}})
    g.throttle()
    call(g, g.docs.documents().batchUpdate(documentId=doc_id,
                                           body={"requests": requests}))


def upsert_doc(session: Session, g: Google, episode: Episode, folder_id: str) -> str:
    """Bring one episode's Doc up to date. Returns what happened:

    ``created``, ``updated`` (text rewritten, maybe renamed too), ``renamed``,
    ``unchanged`` (no API call at all), ``skipped`` (no transcript), ``error``.
    A per-episode failure is stored in ``last_error`` and does not raise.
    """
    transcript = loader.current_transcript(session, episode.id)
    if transcript is None:
        return "skipped"
    text, layer_used = render_plain(session, transcript.id, settings.google_doc_layer,
                                    labels=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    title = doc_title(episode)
    row = _row(session, episode)

    if (row.doc_id and row.text_sha256 == digest and row.doc_title == title
            and row.folder_id == folder_id):
        return "unchanged"

    try:
        outcome = _write(g, row, folder_id, title, text, digest)
    except Exception as exc:  # noqa: BLE001 — one episode must not stop the rest
        from .auth import GoogleAuthError

        if isinstance(exc, GoogleAuthError):
            raise
        row.last_error = short_error(exc)
        session.flush()
        log.warning("google: %s failed: %s", episode.slug, row.last_error)
        return "error"

    row.text_sha256 = digest
    row.doc_title = title
    row.folder_id = folder_id
    row.layer_used = layer_used
    row.syllables = len(text.split())
    row.synced_at = datetime.now(UTC)
    row.last_error = None
    session.flush()
    log.info("google: %s %s", episode.slug, outcome)
    return outcome


def _write(g: Google, row: EpisodeGoogleDoc, folder_id: str, title: str, text: str,
           digest: str) -> str:
    from googleapiclient.errors import HttpError

    if row.doc_id:
        try:
            outcome = None
            # Also true right after an episode is moved to another project: its Doc
            # follows the row into that project's folder.
            if row.synced_at is None or row.folder_id != folder_id:
                _move_into(g, row.doc_id, folder_id)
                outcome = "moved" if row.synced_at is not None else None
            if row.text_sha256 != digest:
                _replace_text(g, row.doc_id, text)
                outcome = "updated"
            if row.doc_title != title:
                g.throttle()
                call(g, g.drive.files().update(fileId=row.doc_id, body={"name": title},
                                               fields="id"))
                outcome = outcome or "renamed"
            return outcome or "unchanged"
        except HttpError as exc:
            if status_of(exc) != 404:
                raise
            log.warning("google: Doc %s is gone (deleted in Drive?); recreating it",
                        row.doc_id)
            row.doc_id = None
    _create(g, row, folder_id, title, text)
    return "created"
