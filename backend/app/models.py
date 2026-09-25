"""SQLAlchemy models for the PLAN §8 schema.

Two layers, deliberately separated (PLAN §0.2):

``transcripts`` / ``words``
    Derived from the immutable raw JSON. Rebuildable — drop and regenerate at will.
``utterances`` / ``utterance_edits``
    The human layer. ``text_asr`` is a frozen copy of the engine's output;
    ``text_verified`` is the verifier's text and is ``NULL`` until someone touches it.
    Every edit is appended to ``utterance_edits``; nothing is overwritten silently.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

EPISODE_STATUSES = (
    "ingested", "queued", "processing", "transcribed", "verifying", "verified", "failed",
)
JOB_KINDS = ("transcribe", "export", "google_sync")
JOB_STATUSES = ("queued", "running", "done", "failed")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint(
            "status in (" + ", ".join(f"'{s}'" for s in EPISODE_STATUSES) + ")",
            name="episodes_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    air_date: Mapped[date | None] = mapped_column(Date)
    audio_path: Mapped[str | None] = mapped_column(Text)
    audio_sha256: Mapped[str | None] = mapped_column(Text)
    duration_s: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ingested")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transcripts: Mapped[list[Transcript]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )


class Job(Base):
    """DB-as-queue (PLAN §6). The worker claims rows with ``FOR UPDATE SKIP LOCKED``."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "kind in (" + ", ".join(f"'{k}'" for k in JOB_KINDS) + ")",
            name="jobs_kind_check",
        ),
        CheckConstraint(
            "status in (" + ", ".join(f"'{s}'" for s in JOB_STATUSES) + ")",
            name="jobs_status_check",
        ),
        Index("ix_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    params: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    log: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    episode: Mapped[Episode | None] = relationship(back_populates="jobs")


class Transcript(Base):
    """One engine run. Immutable: a re-run inserts a new row (PLAN §0.2)."""

    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSONB)
    hotwords_sha256: Mapped[str | None] = mapped_column(Text)
    raw_json_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Filled by the pilot only (PLAN §8).
    wer_vs_reference: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    episode: Mapped[Episode] = relationship(back_populates="transcripts")
    words: Mapped[list[Word]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan"
    )
    utterances: Mapped[list[Utterance]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan"
    )


class Word(Base):
    """Derived from the raw JSON; safe to delete and rebuild."""

    __tablename__ = "words"
    __table_args__ = (
        # Corpus search later (PLAN §8, §11 T6). 'simple' config: no stemming, because
        # a stemmer would erase exactly the morphology the corpus is for.
        Index(
            "ix_words_tsv",
            text("to_tsvector('simple', text)"),
            postgresql_using="gin",
        ),
        Index("ix_words_transcript_start", "transcript_id", "start_s"),
    )

    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    i: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_s: Mapped[float] = mapped_column(Numeric, nullable=False)
    end_s: Mapped[float | None] = mapped_column(Numeric)
    conf: Mapped[float | None] = mapped_column(Numeric)

    transcript: Mapped[Transcript] = relationship(back_populates="words")


class Utterance(Base):
    """The human-editable layer. ``text_asr`` is frozen; ``text_verified`` is theirs."""

    __tablename__ = "utterances"
    __table_args__ = (
        UniqueConstraint("transcript_id", "i", name="uq_utterances_transcript_i"),
        Index("ix_utterances_transcript_start", "transcript_id", "start_s"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    i: Mapped[int] = mapped_column(Integer, nullable=False)
    start_s: Mapped[float] = mapped_column(Numeric, nullable=False)
    end_s: Mapped[float] = mapped_column(Numeric, nullable=False)
    #: Frozen copy from the raw JSON. Never updated.
    text_asr: Mapped[str] = mapped_column(Text, nullable=False)
    #: NULL means untouched. An empty string is a deliberate edit, not "untouched".
    text_verified: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[str | None] = mapped_column(String(128))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Derived readable layer (punctuation + case, app/readable.py). Never exported as
    #: corpus text. ``readable_from`` is the exact text it was computed from; when it
    #: differs from the current text (an edit, a split) the readable text is stale.
    text_readable: Mapped[str | None] = mapped_column(Text)
    readable_from: Mapped[str | None] = mapped_column(Text)
    #: e.g. {'overlap','unclear','music'} (PLAN §8, §10).
    flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )

    transcript: Mapped[Transcript] = relationship(back_populates="utterances")
    edits: Mapped[list[UtteranceEdit]] = relationship(
        back_populates="utterance", cascade="all, delete-orphan"
    )


class UtteranceEdit(Base):
    """Append-only audit log. Never UPDATE or DELETE a row here (PLAN §8)."""

    __tablename__ = "utterance_edits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utterances.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str | None] = mapped_column(Text)
    editor: Mapped[str | None] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    utterance: Mapped[Utterance] = relationship(back_populates="edits")


class Hotword(Base):
    """Contextual-biasing terms (PLAN §2 hotwords, §8 seed list)."""

    __tablename__ = "hotwords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric, nullable=False, default=1.0)
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Setting(Base):
    """Pipeline knobs chosen in the pilot (blank_penalty, thresholds…) — PLAN §8."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)


USER_ROLES = ("admin", "editor")


class User(Base):
    """A login account. Admins create them; there is no public sign-up.

    ``username`` is what lands in ``utterance_edits.editor`` / ``verified_by``, so it is
    stable: renaming someone changes ``display_name`` only. ``session_version`` is bumped
    on a password reset, role change or disable, which invalidates every cookie issued
    before it.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role in {USER_ROLES!r}", name="users_role_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoogleRepoState(Base):
    """Key/value state of the Google repository: ``folder_id``, ``sheet_id``… (T3)."""

    __tablename__ = "google_repo_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EpisodeGoogleDoc(Base):
    """The Google Doc of one episode. ``episode_id`` NULL = orphan (episode deleted)."""

    __tablename__ = "episode_google_doc"

    id: Mapped[uuid.UUID] = _uuid_pk()
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="SET NULL"), unique=True
    )
    doc_id: Mapped[str | None] = mapped_column(Text)
    text_sha256: Mapped[str | None] = mapped_column(Text)
    layer_used: Mapped[str | None] = mapped_column(Text)
    doc_title: Mapped[str | None] = mapped_column(Text)
    #: ``len(text.split())`` of the Doc body, for the Sheet's Syllables column.
    syllables: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
