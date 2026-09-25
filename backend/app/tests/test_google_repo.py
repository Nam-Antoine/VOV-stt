"""Google Sheet + Docs repository (GOOGLE_REPO_PLAN Task 9). Every Google call is faked.

The fake records each request and keeps just enough state (files, parents, Doc text,
Sheet values) for the sync logic to be checked end to end. No network, no database.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

pytest.importorskip("googleapiclient")
pytest.importorskip("google_auth_oauthlib")

import httplib2  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

from app.config import settings  # noqa: E402
from app.google_repo import auth, docs, sheet, state, sync  # noqa: E402
from app.google_repo import health as health_mod  # noqa: E402
from app.google_repo.client import Google  # noqa: E402
from app.models import EpisodeGoogleDoc  # noqa: E402

WRITES = {
    "drive.files.create", "drive.files.update",
    "docs.documents.create", "docs.documents.batchUpdate",
    "sheets.spreadsheets.batchUpdate",
    "sheets.spreadsheets.values.clear", "sheets.spreadsheets.values.update",
}


def http_error(status: int) -> HttpError:
    return HttpError(httplib2.Response({"status": status}),
                     json.dumps({"error": {"message": f"fake {status}"}}).encode())


# --- the fake Google ----------------------------------------------------------------

class FakeGoogleAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.files: dict[str, dict] = {"root": {"name": "My Drive", "parents": []}}
        self.fail: dict[str, list[HttpError]] = {}
        self._n = 0

    # sub-resources are called with no arguments; methods with keyword arguments
    def service(self, name: str) -> Resource:
        return Resource(self, name)

    def writes(self) -> list[str]:
        return [m for m, _ in self.calls if m in WRITES]

    def _new_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def _file(self, file_id: str) -> dict:
        if file_id not in self.files:
            raise http_error(404)
        return self.files[file_id]

    def handle(self, method: str, kw: dict) -> dict:
        self.calls.append((method, kw))
        if self.fail.get(method):
            raise self.fail[method].pop(0)
        if method == "drive.files.create":
            body = kw["body"]
            fid = self._new_id("f")
            self.files[fid] = {"name": body["name"], "mimeType": body.get("mimeType"),
                               "parents": body.get("parents", ["root"]), "values": []}
            return {"id": fid}
        if method == "drive.files.get":
            return {"parents": list(self._file(kw["fileId"])["parents"])}
        if method == "drive.files.update":
            f = self._file(kw["fileId"])
            if kw.get("body", {}).get("name"):
                f["name"] = kw["body"]["name"]
            if kw.get("addParents"):
                drop = set(filter(None, (kw.get("removeParents") or "").split(",")))
                f["parents"] = [p for p in f["parents"] if p not in drop]
                f["parents"].append(kw["addParents"])
            return {"id": kw["fileId"]}
        if method == "drive.about.get":
            return {"user": {"emailAddress": "owner@example.com", "displayName": "Owner"}}
        if method == "docs.documents.create":
            did = self._new_id("d")
            self.files[did] = {"name": kw["body"]["title"], "parents": ["root"], "text": ""}
            return {"documentId": did}
        if method == "docs.documents.get":
            text = self._file(kw["documentId"])["text"]
            return {"body": {"content": [{"endIndex": 1}, {"endIndex": len(text) + 2}]}}
        if method == "docs.documents.batchUpdate":
            f = self._file(kw["documentId"])
            for r in kw["body"]["requests"]:
                if "deleteContentRange" in r:
                    f["text"] = ""
                if "insertText" in r:
                    f["text"] = r["insertText"]["text"] + f["text"]
            return {}
        if method == "sheets.spreadsheets.get":
            self._file(kw["spreadsheetId"])
            return {"sheets": [{"properties": {"sheetId": 0}}]}
        if method == "sheets.spreadsheets.batchUpdate":
            self._file(kw["spreadsheetId"])["frozen"] = True
            return {}
        if method == "sheets.spreadsheets.values.clear":
            self._file(kw["spreadsheetId"])["values"] = []
            return {}
        if method == "sheets.spreadsheets.values.update":
            self._file(kw["spreadsheetId"])["values"] = kw["body"]["values"]
            return {}
        raise AssertionError(f"unexpected call {method}")


class Resource:
    def __init__(self, api: FakeGoogleAPI, path: str) -> None:
        self.api, self.path = api, path

    def __getattr__(self, name: str):
        def method(**kw):
            if not kw:
                return Resource(self.api, f"{self.path}.{name}")
            return SimpleNamespace(
                execute=lambda: self.api.handle(f"{self.path}.{name}", kw))
        return method


def make_google(api: FakeGoogleAPI) -> tuple[Google, list[float]]:
    slept: list[float] = []
    clock = iter(range(0, 10**9, 10))  # 10 s apart: the rate limit never waits
    g = Google(drive=api.service("drive"), docs=api.service("docs"),
               sheets=api.service("sheets"), sleep=slept.append,
               clock=lambda: float(next(clock)))
    return g, slept


# --- a database stand-in --------------------------------------------------------------

class World:
    """Episodes, their current text, and the two Google tables, all in memory."""

    def __init__(self, monkeypatch, n: int = 2) -> None:
        self.kv: dict[str, str | None] = {}
        self.rows: dict[uuid.UUID, EpisodeGoogleDoc] = {}
        self.episodes = [
            SimpleNamespace(id=uuid.uuid4(), slug=f"2020010{k + 1}-ep{k}",
                            title=f"Tập {k}", air_date=date(2020, 1, k + 1),
                            duration_s=900.0, source_url=f"https://vov.example/{k}",
                            status="transcribed")
            for k in range(n)
        ]
        self.text = {e.id: f"Đoạn một của tập {k}.\n\nĐoạn hai.\n"
                     for k, e in enumerate(self.episodes)}
        self.session = SimpleNamespace(flush=lambda: None, commit=lambda: None)

        monkeypatch.setattr(state, "get", lambda s, k: self.kv.get(k))
        monkeypatch.setattr(state, "put", lambda s, k, v: self.kv.__setitem__(k, v))
        monkeypatch.setattr(docs.loader, "current_transcript",
                            lambda s, eid: SimpleNamespace(id=eid))
        monkeypatch.setattr(docs, "render_plain",
                            lambda s, tid, layer, labels: (self._render(tid, labels),
                                                           "readable"))
        monkeypatch.setattr(docs, "_row", lambda s, ep: self.rows.setdefault(
            ep.id, EpisodeGoogleDoc(episode_id=ep.id)))
        monkeypatch.setattr(sheet, "rows", lambda s: [
            [e.slug, sheet.title_cell(e.title, getattr(self.rows.get(e.id), "doc_id", None)),
             e.air_date.isoformat(), sheet.duration_text(e.duration_s), e.source_url,
             e.status, "", getattr(self.rows.get(e.id), "syllables", "")]
            for e in self.episodes
        ])

    def _render(self, tid, labels):
        assert labels is False
        return self.text[tid]

    def sync(self, g: Google) -> dict[str, int]:
        return sync.sync(self.session, self.episodes, g=g, full=True)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "google_repo_enabled", True)
    monkeypatch.setattr(settings, "google_doc_layer", "readable")


# --- sync behaviour -------------------------------------------------------------------

def test_first_sync_creates_folder_sheet_and_docs(monkeypatch, enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    counts = world.sync(g)

    assert counts == {"created": 2, "sheet_written": 1}
    folder = world.kv[state.FOLDER_ID]
    assert api.files[folder]["name"] == settings.google_folder_name
    sheet_file = api.files[world.kv[state.SHEET_ID]]
    assert sheet_file["parents"] == [folder] and sheet_file.get("frozen")
    for e in world.episodes:
        doc = api.files[world.rows[e.id].doc_id]
        assert doc["parents"] == [folder]
        assert doc["text"] == world.text[e.id]
        assert doc["name"] == f"{e.slug} — {e.title}"
        assert world.rows[e.id].syllables == len(world.text[e.id].split())
    values = sheet_file["values"]
    assert values[0] == sheet.HEADER
    assert values[1][1].startswith('=HYPERLINK("https://docs.google.com/document/d/')


def test_second_identical_sync_makes_zero_writes(monkeypatch, enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    world.sync(g)
    api.calls.clear()

    counts = world.sync(g)
    assert api.writes() == []
    assert api.calls == []  # no reads either: nothing changed, nothing asked
    assert counts == {"unchanged": 2, "sheet_written": 0}


def test_a_text_change_rewrites_one_doc(monkeypatch, enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    world.sync(g)
    api.calls.clear()
    first, second = world.episodes
    world.text[first.id] = "Văn bản mới.\n"

    counts = world.sync(g)
    assert counts["updated"] == 1 and counts["unchanged"] == 1
    batch = [kw for m, kw in api.calls if m == "docs.documents.batchUpdate"]
    assert len(batch) == 1 and batch[0]["documentId"] == world.rows[first.id].doc_id
    assert "deleteContentRange" in batch[0]["body"]["requests"][0]
    assert api.files[world.rows[first.id].doc_id]["text"] == "Văn bản mới.\n"
    assert api.files[world.rows[second.id].doc_id]["text"] == world.text[second.id]


def test_a_title_change_renames_the_doc(monkeypatch, enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    world.sync(g)
    api.calls.clear()
    first = world.episodes[0]
    first.title = 'Tên "mới"'

    counts = world.sync(g)
    assert counts["renamed"] == 1
    assert [m for m in api.writes() if m.startswith("docs.")] == []
    assert api.files[world.rows[first.id].doc_id]["name"] == f'{first.slug} — Tên "mới"'
    title = api.files[world.kv[state.SHEET_ID]]["values"][1][1]
    assert title.endswith('"Tên ""mới""")')


def test_a_deleted_doc_is_recreated(monkeypatch, enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    world.sync(g)
    first = world.episodes[0]
    old = world.rows[first.id].doc_id
    del api.files[old]                       # someone deleted it in Drive
    world.text[first.id] = "Sửa sau khi xoá.\n"

    counts = world.sync(g)
    new = world.rows[first.id].doc_id
    assert counts["created"] == 1 and new != old
    assert api.files[new]["text"] == "Sửa sau khi xoá.\n"
    assert api.files[new]["parents"] == [world.kv[state.FOLDER_ID]]
    assert world.rows[first.id].last_error is None


def test_429_is_retried_then_succeeds(monkeypatch, enabled):
    world, api = World(monkeypatch, n=1), FakeGoogleAPI()
    g, slept = make_google(api)
    api.fail["docs.documents.create"] = [http_error(429), http_error(503)]

    counts = world.sync(g)
    assert counts["created"] == 1
    assert [m for m, _ in api.calls].count("docs.documents.create") == 3
    assert slept == [2.0, 4.0]


def test_a_persistent_failure_is_stored_and_the_next_episode_still_syncs(monkeypatch,
                                                                          enabled):
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    api.fail["docs.documents.create"] = [http_error(403)]

    counts = world.sync(g)
    assert counts["error"] == 1 and counts["created"] == 1
    first, second = world.episodes
    assert world.rows[first.id].last_error.startswith("HTTP 403")
    assert world.rows[second.id].last_error is None


def test_doc_writes_are_rate_limited(monkeypatch, enabled):
    api = FakeGoogleAPI()
    slept: list[float] = []
    g = Google(drive=api.service("drive"), docs=api.service("docs"),
               sheets=api.service("sheets"), sleep=slept.append, clock=lambda: 100.0)
    g.throttle()
    g.throttle()
    assert slept == [pytest.approx(1.1)]


def test_disabled_means_no_calls_at_all(monkeypatch):
    monkeypatch.setattr(settings, "google_repo_enabled", False)
    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    monkeypatch.setattr(sync, "connect", lambda: pytest.fail("connected while disabled"))

    assert world.sync(g) == {}
    assert sync.enqueue(world.session, world.episodes[0].id) is False
    assert sync.handle_job(world.session, {"episode_id": None}).startswith("google "
                                                                           "repository")
    assert health_mod.repo_health() == "disabled"
    assert api.calls == []


def test_enqueue_is_one_try_and_one_pending_job_per_episode(monkeypatch, enabled):
    added = []
    pending = {"n": 0}
    session = SimpleNamespace(scalar=lambda q: pending["n"], add=added.append,
                              flush=lambda: None)
    ep = uuid.uuid4()
    assert sync.enqueue_after_edit(session, ep) is True
    job = added[0]
    assert job.kind == "google_sync" and job.max_attempts == 1
    assert "not_before" in job.params
    pending["n"] = 1
    assert sync.enqueue_after_edit(session, ep) is False
    assert len(added) == 1


# --- the Sheet ------------------------------------------------------------------------

def test_sheet_header_exact():
    assert sheet.HEADER == [
        "Mã tập", "Tên tập (mở bản chép lời)", "Ngày phát", "Thời lượng", "Link gốc (audio)",
        "Trạng thái", "Người duyệt", "Số âm tiết",
    ]
    lowered = [h.lower() for h in sheet.HEADER]
    for banned in ("guest", "mc"):
        assert not any(banned in h.split() for h in lowered)


def test_duration_stays_text_and_titles_escape_quotes():
    assert sheet.duration_text(900.4) == "'15:00"
    assert sheet.duration_text(None) == ""
    assert sheet.title_cell('A "b"', None) == 'A "b"'
    assert sheet.title_cell('A "b"', "X") == (
        '=HYPERLINK("https://docs.google.com/document/d/X/edit"; "A ""b""")')


# --- auth -----------------------------------------------------------------------------

SECRETS = ("ya29.SECRET-ACCESS-TOKEN", "1//SECRET-REFRESH-TOKEN", "GOCSPX-SECRET-CLIENT")


def write_token(path, *, expired=True):
    path.write_text(json.dumps({
        "token": SECRETS[0], "refresh_token": SECRETS[1],
        "client_id": "123.apps.googleusercontent.com", "client_secret": SECRETS[2],
        "token_uri": "https://oauth2.googleapis.com/token", "scopes": auth.SCOPES,
        "expiry": "2020-01-01T00:00:00Z" if expired else "2999-01-01T00:00:00Z",
    }), encoding="utf-8")


def test_invalid_grant_is_a_clear_error_and_not_retried(tmp_path, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    token = tmp_path / "token.json"
    write_token(token)
    tries = []

    def refuse(self, request):
        tries.append(1)
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", refuse)
    with pytest.raises(auth.GoogleAuthError) as err:
        auth.get_credentials(token)
    assert len(tries) == 1
    assert "revoked or expired" in str(err.value) and "--init" in str(err.value)


def test_missing_token_is_a_clear_error(tmp_path):
    with pytest.raises(auth.GoogleAuthError, match="no Google token"):
        auth.get_credentials(tmp_path / "token.json")


def test_rotated_refresh_token_is_written_back_atomically(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    token = tmp_path / "token.json"
    write_token(token)

    def rotate(self, request):
        self.token = "ya29.NEW"
        self._refresh_token = "1//NEW-REFRESH"
        self.expiry = None

    monkeypatch.setattr(Credentials, "refresh", rotate)
    auth.get_credentials(token)
    saved = json.loads(token.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "1//NEW-REFRESH"
    assert token.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["token.json"]  # no temp file left


def test_health_reports_token_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "google_repo_enabled", True)
    monkeypatch.setattr(settings, "google_token_path", tmp_path / "missing.json")
    monkeypatch.setattr(health_mod, "_cache", None)
    assert health_mod.repo_health() == "token_invalid"


def test_no_secrets_logged(tmp_path, monkeypatch, caplog, enabled):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    caplog.set_level(logging.DEBUG)
    token = tmp_path / "token.json"
    write_token(token)
    monkeypatch.setattr(Credentials, "refresh", lambda self, r: (_ for _ in ()).throw(
        RefreshError(f"invalid_grant for {SECRETS[1]}")))
    with pytest.raises(auth.GoogleAuthError) as err:
        auth.get_credentials(token)
    messages = [str(err.value)]

    world, api = World(monkeypatch), FakeGoogleAPI()
    g, _ = make_google(api)
    api.fail["docs.documents.create"] = [http_error(401)]
    world.sync(g)
    messages += [r.last_error or "" for r in world.rows.values()]

    text = caplog.text + "\n".join(messages)
    for secret in SECRETS:
        assert secret not in text
