"""Pydantic v2 request/response models for the §9 API.

TODO(T3): these are the shapes the endpoints will return; the handlers themselves are
stubs until the pilot gate (T2) is signed off.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    ok: bool = True


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


class SpeakerOut(ORMModel):
    cluster: int
    label: str | None = None


class SpeakerLabel(BaseModel):
    label: str


class EpisodeDetail(EpisodeOut):
    """Episode + current transcript summary + speakers (PLAN §9)."""

    current_transcript_id: uuid.UUID | None = None
    n_utterances: int = 0
    n_verified: int = 0
    speakers: list[SpeakerOut] = Field(default_factory=list)


# --- jobs -------------------------------------------------------------------

class JobOut(ORMModel):
    id: uuid.UUID
    episode_id: uuid.UUID | None
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
    diarize: bool = True
    diar_threshold: float | None = None
    vad_threshold: float | None = None


# --- transcripts ------------------------------------------------------------

class WordOut(ORMModel):
    i: int
    text: str
    start_s: float
    end_s: float | None = None
    conf: float | None = None
    speaker: int


class UtteranceOut(ORMModel):
    id: uuid.UUID
    i: int
    speaker: int
    start_s: float
    end_s: float
    text_asr: str
    text_verified: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    flags: list[str] = Field(default_factory=list)


class TranscriptOut(ORMModel):
    id: uuid.UUID
    episode_id: uuid.UUID
    engine: str
    engine_version: str | None = None
    params: dict | None = None
    hotwords_sha256: str | None = None
    created_at: datetime
    words: list[WordOut] = Field(default_factory=list)
    utterances: list[UtteranceOut] = Field(default_factory=list)
    speakers: list[SpeakerOut] = Field(default_factory=list)


class UtterancePatch(BaseModel):
    """PATCH /utterances/{id}.

    ``text_verified`` is stored exactly as sent. The API must not trim, case-fold or
    punctuate it (CLAUDE.md rule 1) — the editor disables spellcheck and autocorrect for
    the same reason (PLAN §10).
    """

    text_verified: str | None = None
    speaker: int | None = None
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
