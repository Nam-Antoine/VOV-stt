"""Default role labels for a freshly diarized episode: host and main guest.

PLAN §0.3 / CLAUDE.md rule 9: this is **not** speaker identification. Nothing is
compared across episodes and no voice is matched to a person; the roles come from
turn-taking inside one episode only, and are written as ordinary free-text labels the
verifier can overwrite. Everyone else (callers, vox pops) stays unnamed.

The shape of a talk-show episode, measured on the first transcribed "Đàn bà 30+"
episodes: the host takes the most turns (opens after the jingle, links every segment,
closes the show); the invited guest talks longest in fewer, longer turns; callers and
vox pops are one or two short turns each.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import loader
from .models import Speaker, Utterance

HOST = "Dẫn chương trình"
GUEST = "Khách mời"

#: A cluster must hold at least this share of the episode's speech to get a role, so a
#: chatty but brief voice (a jingle split into many pieces) can't pass as the host.
MIN_SHARE = 0.10


def guess_roles(turns: Iterable[tuple[int, float, float]]) -> dict[int, str]:
    """``{cluster: role}`` from ``(speaker, start_s, end_s)`` turns of one episode."""
    stats: dict[int, list[float]] = {}   # cluster -> [talk_s, n_turns, first_start]
    for speaker, start, end in turns:
        if speaker < 0:                  # speakers still pending
            return {}
        s = stats.setdefault(speaker, [0.0, 0, start])
        s[0] += max(0.0, end - start)
        s[1] += 1
        s[2] = min(s[2], start)

    total = sum(s[0] for s in stats.values())
    main = {c: s for c, s in stats.items() if total and s[0] >= MIN_SHARE * total}
    if not main:
        return {}
    host = max(main, key=lambda c: (main[c][1], -main[c][2]))
    roles = {host: HOST}
    rest = [c for c in main if c != host]
    if rest:
        roles[max(rest, key=lambda c: main[c][0])] = GUEST
    return roles


def label_roles(session: Session, episode_id: uuid.UUID) -> dict[int, str]:
    """Write default role labels unless the episode already has any label.

    Any existing label means a person has named speakers (or a previous run already
    did), so nothing is touched — a re-run never overwrites a verifier's work.
    """
    labelled = session.scalar(
        select(func.count()).select_from(Speaker)
        .where(Speaker.episode_id == episode_id, Speaker.label.is_not(None),
               Speaker.label != "")
    )
    if labelled:
        return {}
    transcript = loader.current_transcript(session, episode_id)
    if transcript is None or transcript.speakers_pending:
        return {}
    turns = session.execute(
        select(Utterance.speaker, Utterance.start_s, Utterance.end_s)
        .where(Utterance.transcript_id == transcript.id)
    ).all()
    roles = guess_roles((int(s), float(a), float(b)) for s, a, b in turns)
    for cluster, role in roles.items():
        row = session.get(Speaker, {"episode_id": episode_id, "cluster": cluster})
        if row is None:
            session.add(Speaker(episode_id=episode_id, cluster=cluster, label=role))
        else:
            row.label = role
    session.flush()
    return roles
