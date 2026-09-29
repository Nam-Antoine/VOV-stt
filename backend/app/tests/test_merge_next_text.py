"""``merged_verified_text`` (api/utterances.py) — what text_verified becomes after a
merge. Pure function, no database: the same style as pipeline/merge.py's tests.

Regression for a real bug: computing the un-verified fallback from ``text_asr`` after
it had already been overwritten with the merged pair duplicated the other side's words
into ``text_verified``.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.api.utterances import merged_verified_text


def u(text_asr: str, text_verified: str | None = None):
    return SimpleNamespace(text_asr=text_asr, text_verified=text_verified)


def test_neither_side_verified_stays_unverified():
    assert merged_verified_text(u("xin chào"), u("các bạn")) is None


def test_only_the_left_side_verified():
    left = u("xin chào", "Xin chào")
    right = u("các bạn")
    assert merged_verified_text(left, right) == "Xin chào các bạn"


def test_only_the_right_side_verified_does_not_duplicate_the_left():
    """The bug: this used to come out as 'xin chào các bạn các bạn ạ'."""
    left = u("xin chào")
    right = u("các bạn", "các bạn ạ")
    assert merged_verified_text(left, right) == "xin chào các bạn ạ"


def test_both_sides_verified():
    left = u("xin chào", "Xin chào")
    right = u("các bạn", "các bạn nhé")
    assert merged_verified_text(left, right) == "Xin chào các bạn nhé"


def test_a_deliberate_empty_verified_text_still_counts_as_verified():
    # '' means "no speech here" (CLAUDE.md / schemas.py), not "untouched" — must not be
    # treated the same as None.
    left = u("um", "")
    right = u("xin chào")
    assert merged_verified_text(left, right) == " xin chào"
