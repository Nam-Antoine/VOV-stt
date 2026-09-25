"""ELAN export structure (PLAN §11 T3).

Opens the generated EAF with ``xml.etree`` and asserts there is one ``transcript`` tier
(no speaker tiers, even for an old raw JSON that still carries speaker clusters) and
that every annotation references two real time slots. An EAF with a dangling slot ref
opens in ELAN as an empty tier, which looks like data loss to a verifier.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.exports import eaf


def doc_with(n_speakers: int = 3, per_speaker: int = 4) -> dict:
    utterances, words, idx = [], [], 0
    t = 0.0
    for u in range(n_speakers * per_speaker):
        speaker = u % n_speakers
        start, end = t, t + 1.5
        t = end + 0.6
        utterances.append(
            {
                "i": u, "speaker": speaker, "start": start, "end": end,
                "word_ids": [idx, idx + 1], "text": f"à ừ thì {speaker}",
            }
        )
        words += [
            {"i": idx, "text": "à", "start": start, "end": start + 0.2,
             "conf": -0.1, "speaker": speaker},
            {"i": idx + 1, "text": "ừ", "start": start + 0.2, "end": end,
             "conf": -0.2, "speaker": speaker},
        ]
        idx += 2
    return {
        "schema_version": 1,
        "episode_id": "11111111-1111-1111-1111-111111111111",
        "source": {"filename": "ep042.mp3", "url": None, "sha256": "0" * 64},
        "audio": {"duration_s": t, "sample_rate": 16000, "channels": 1},
        "engine": {"name": "zipformer-30m-rnnt-6000h", "params": {}},
        "vad": {"model": "silero_vad.onnx", "segments": []},
        "diarization": {"segments": []},
        "words": words,
        "utterances": utterances,
        "created_at": "2026-09-22T09:00:00+07:00",
    }


@pytest.fixture
def root():
    return ET.fromstring(eaf.render(doc_with()))


def test_document_declares_eaf_30(root):
    assert root.tag == "ANNOTATION_DOCUMENT"
    assert root.get("FORMAT") == "3.0"


def test_one_tier_whatever_the_speaker_clusters(root):
    # doc_with() is an old-style document with three speaker clusters.
    tiers = root.findall("TIER")
    assert [t.get("TIER_ID") for t in tiers] == ["transcript"]
    assert all(t.get("PARTICIPANT") is None for t in tiers)


def test_every_annotation_has_two_resolvable_time_slots(root):
    slots = {
        s.get("TIME_SLOT_ID"): int(s.get("TIME_VALUE"))
        for s in root.find("TIME_ORDER").findall("TIME_SLOT")
    }
    annotations = root.findall(".//ALIGNABLE_ANNOTATION")
    assert annotations
    for ann in annotations:
        ref1, ref2 = ann.get("TIME_SLOT_REF1"), ann.get("TIME_SLOT_REF2")
        assert ref1 in slots and ref2 in slots
        assert slots[ref2] >= slots[ref1]


def test_annotation_ids_are_unique(root):
    ids = [a.get("ANNOTATION_ID") for a in root.findall(".//ALIGNABLE_ANNOTATION")]
    assert len(ids) == len(set(ids)) == 12


def test_every_utterance_appears_exactly_once(root):
    values = [v.text for v in root.iter("ANNOTATION_VALUE")]
    assert len(values) == 12


def test_time_values_are_milliseconds(root):
    doc = doc_with()
    first = doc["utterances"][0]
    slots = {
        s.get("TIME_SLOT_ID"): int(s.get("TIME_VALUE"))
        for s in root.find("TIME_ORDER").findall("TIME_SLOT")
    }
    assert slots["ts1"] == round(first["start"] * 1000)
    assert slots["ts2"] == round(first["end"] * 1000)


def test_linguistic_type_is_declared_and_referenced(root):
    declared = {lt.get("LINGUISTIC_TYPE_ID") for lt in root.findall("LINGUISTIC_TYPE")}
    referenced = {t.get("LINGUISTIC_TYPE_REF") for t in root.findall("TIER")}
    assert referenced <= declared


def test_media_descriptor_points_at_the_episode(root):
    md = root.find("HEADER/MEDIA_DESCRIPTOR")
    assert md is not None
    assert md.get("MEDIA_URL").endswith("ep042.mp3")


def test_empty_document_still_parses():
    doc = doc_with()
    doc["utterances"], doc["words"] = [], []
    root = ET.fromstring(eaf.render(doc))
    assert root.find("TIME_ORDER") is not None
    assert [len(t.findall("ANNOTATION")) for t in root.findall("TIER")] == [0]
