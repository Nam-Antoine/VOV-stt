"""Hotword suggestions from corrections: the licence-safe way the model's mistakes feed back."""

import uuid

from app.corrections import correction_spans, suggest

EP = uuid.uuid4()


def test_a_misheard_name_is_suggested_as_typed_words():
    asr = "CÙNG VỊ KHÁCH MỜI QUEN THUỘC LÀ NHÀ VĂN ZELLI XIN KÍNH CHÀO"
    fixed = "cùng vị khách mời quen thuộc là nhà văn Di Li xin kính chào"
    assert correction_spans(asr, fixed) == [("ZELLI", "Di Li")]


def test_a_one_word_fix_keeps_its_neighbours():
    asr = "CHÚNG TA LÀ AN BÀ THẾ NHƯNG"
    fixed = "chúng ta là đàn bà thế nhưng"
    assert correction_spans(asr, fixed) == [("LÀ AN BÀ", "là đàn bà")]


def test_case_and_punctuation_are_not_corrections():
    assert correction_spans("TỚI HÀ NỘI NGHE VOV2", "tới Hà Nội, nghe VOV2.") == []


def test_deletions_and_long_rewrites_are_not_suggested():
    assert correction_spans("Ờ THÌ THÌ EM", "ờ thì em") == []
    rewrite = "một hai ba bốn năm sáu bảy"
    assert correction_spans("KHÁC HẲN", rewrite) == []


def test_suggestions_count_repeats_and_skip_existing_hotwords():
    rows = [
        ("NHÀ VĂN ZELLI", "nhà văn Di Li", EP, "Khủng hoảng tuổi 30"),
        ("CHỊ ZELLI ƠI", "chị Di Li ơi", EP, "Đàn bà vụng"),
        ("CHÚNG TA LÀ AN BÀ", "chúng ta là đàn bà", EP, "Khủng hoảng tuổi 30"),
    ]
    got = suggest(rows, existing={"LÀ ĐÀN BÀ"})
    assert [(s.term, s.count) for s in got] == [("DI LI", 2)]
    assert got[0].examples[0] == {"episode_id": str(EP), "title": "Khủng hoảng tuổi 30",
                                  "heard": "ZELLI", "corrected": "Di Li"}
