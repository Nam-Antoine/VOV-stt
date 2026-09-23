"""A hotword the model's BPE cannot encode is silently inert — make that visible."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.hotwords import unencodable

pytest.importorskip("sentencepiece")

BPE = Path(__file__).resolve().parents[3] / "models" / "zipformer-30m-rnnt-6000h" / "bpe.model"
pytestmark = pytest.mark.skipif(not BPE.exists(), reason="ASR model not downloaded")


@pytest.mark.parametrize("term", ["ĐÀN BÀ BA MƯƠI CỘNG", "THANH HUYỀN", "QUẢN CHỒNG"])
def test_uppercase_spoken_form_is_encodable(term):
    assert unencodable(term, BPE) == []


@pytest.mark.parametrize("term,bad", [
    ("Thanh Huyền", ["Thanh", "Huyền"]),
    ("quản chồng", ["quản", "chồng"]),
    ("Đàn bà 30+", ["Đàn", "bà"]),
])
def test_mixed_case_is_reported_word_by_word(term, bad):
    assert unencodable(term, BPE) == bad
