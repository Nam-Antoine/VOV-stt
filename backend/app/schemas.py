"""Pydantic v2 request/response models for the §9 API.

TODO(T3): these are the shapes the endpoints will return; the handlers themselves are
stubs until the pilot gate (T2) is signed off.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    ok: bool = True


class Me(BaseModel):
    username: str
    display_name: str | None = None
    role: str
    #: False: the site has no login; the SPA hides sign-out and account pages.
    auth_enabled: bool = True


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


# Usernames are login handles, not names: lower-case ASCII so "Nam" and "nam" can't be
# two accounts. The person's real name goes in display_name.
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,31}$"


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "editor"] = "editor"
    password: str = Field(max_length=256)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "editor"] | None = None
    is_active: bool | None = None
    #: Set by an admin to reset a forgotten password; signs the user out everywhere.
    password: str | None = Field(default=None, max_length=256)


# --- episodes ---------------------------------------------------------------

class EpisodeBase(BaseModel):
    slug: str
    title: str | None = None
    source_url: str | None = None
    air_date: date | None = None


class EpisodeFromUrl(BaseModel):
    url: str
    title: str | None = None
    air_date: date | None = None


class EpisodeOut(ORMModel, EpisodeBase):
    id: uuid.UUID
    audio_path: str | None = None
    audio_sha256: str | None = None
    duration_s: float | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class EpisodeDetail(EpisodeOut):
    """Episode + current transcript summary (PLAN §9)."""

    current_transcript_id: uuid.UUID | None = None
    n_utterances: int = 0
    n_verified: int = 0
    n_words: int = 0


class EpisodeListItem(EpisodeOut):
    """Row shape for the Episodes table: the transcript counts."""

    current_transcript_id: uuid.UUID | None = None
    n_utterances: int = 0
    n_verified: int = 0


# --- jobs -------------------------------------------------------------------

class JobOut(ORMModel):
    id: uuid.UUID
    episode_id: uuid.UUID | None
    episode_title: str | None = None
    kind: str
    status: str
    attempts: int
    max_attempts: int
    params: dict | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobLog(BaseModel):
    id: uuid.UUID
    log: str = ""


class TranscribeRequest(BaseModel):
    """Optional per-run overrides of the §4.3 knobs."""

    blank_penalty: float | None = None
    decoding_method: str | None = None
    hotwords: bool = True
    vad_threshold: float | None = None


# --- transcripts ------------------------------------------------------------

class WordOut(ORMModel):
    i: int
    text: str
    start_s: float
    end_s: float | None = None
    conf: float | None = None


class UtteranceOut(ORMModel):
    id: uuid.UUID
    i: int
    start_s: float
    end_s: float
    text_asr: str
    text_verified: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    flags: list[str] = Field(default_factory=list)
    #: Punctuated, cased reading of the current text (derived; never corpus text).
    #: None when not computed yet or stale after an edit.
    text_readable: str | None = None


class TranscriptOut(ORMModel):
    id: uuid.UUID
    episode_id: uuid.UUID
    engine: str
    engine_version: str | None = None
    params: dict | None = None
    hotwords_sha256: str | None = None
    created_at: datetime
    #: Whether the readable layer can be computed on this host (model present).
    readable_available: bool = False
    words: list[WordOut] = Field(default_factory=list)
    utterances: list[UtteranceOut] = Field(default_factory=list)


class UtterancePatch(BaseModel):
    """PATCH /utterances/{id}.

    ``text_verified`` is stored exactly as sent. The API must not trim, case-fold or
    punctuate it (CLAUDE.md rule 1) — the editor disables spellcheck and autocorrect for
    the same reason (PLAN §10).
    """

    text_verified: str | None = None
    flags: list[str] | None = None
    start_s: float | None = None
    end_s: float | None = None


class UtteranceSplit(BaseModel):
    at_word_i: int


# --- hotwords ---------------------------------------------------------------

class HotwordIn(BaseModel):
    term: str
    weight: float = 1.0
    note: str | None = None
    active: bool = True


class HotwordPatch(BaseModel):
    term: str | None = None
    weight: float | None = None
    note: str | None = None
    active: bool | None = None


class HotwordOut(ORMModel, HotwordIn):
    id: int
    created_at: datetime


class CorrectionExample(BaseModel):
    episode_id: uuid.UUID
    title: str
    heard: str          # the engine's words
    corrected: str      # as the verifier typed them


class HotwordSuggestion(BaseModel):
    term: str
    count: int
    examples: list[CorrectionExample]


# --- misc -------------------------------------------------------------------

class Stats(BaseModel):
    episodes_by_status: dict[str, int] = Field(default_factory=dict)
    hours_transcribed: float = 0.0
    hours_verified: float = 0.0
    mean_conf: float | None = None


class Health(BaseModel):
    ok: bool
    db: bool
    models: dict[str, bool]
    worker_heartbeat_s: float | None = None
    version: str
    # False → the Word/PDF/TXT downloads answer 503 (no punctuation model installed).
    readable_available: bool = False
    #: disabled | ok | token_invalid | error: <short reason> (GOOGLE_REPO_PLAN Task 8).
    google_repo: str = "disabled"


class GoogleRepoOut(BaseModel):
    enabled: bool
    sheet_url: str | None = None
    #: ISO time of the last ``--all`` sync, UTC.
    last_full_sync: str | None = None
