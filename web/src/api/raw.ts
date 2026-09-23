// Adapter: PLAN §5 raw JSON -> the shapes the API will serve (PLAN §9).
//
// The T3 endpoint GET /transcripts/{id} will return exactly this, built from the same
// raw JSON server-side. Keeping one adapter means the Episode screen is written against
// the real contract now and does not need rewriting when the endpoint lands.
//
// Nothing here alters text. Field renames only (start -> start_s), because the DB
// columns are named differently from the JSON keys.

import type { Speaker, Transcript, Utterance, Word } from './types'

/** The PLAN §5 document, as written by `python -m app.pipeline.run`. */
export interface RawDoc {
  schema_version: number
  episode_id: string
  source: { filename: string; url: string | null; sha256: string }
  audio: { duration_s: number; sample_rate: number; channels: number }
  engine: {
    name: string
    hf_repo?: string
    sherpa_onnx_version?: string
    params?: Record<string, unknown>
  }
  vad: { model: string; segments: [number, number][] }
  diarization: {
    segmentation?: string
    embedding?: string
    threshold?: number
    segments: { start: number; end: number; speaker: number }[]
  } | null
  words: {
    i: number
    text: string
    start: number
    end: number | null
    conf: number | null
    speaker: number
  }[]
  utterances: {
    i: number
    speaker: number
    start: number
    end: number
    word_ids: number[]
    text: string
  }[]
  created_at: string
  timing?: {
    total_s: number
    realtime_factor: number | null
    peak_rss_mb: number
    stages_s: Record<string, number>
  }
}

export function wordsFromRaw(doc: RawDoc): Word[] {
  return doc.words.map((w) => ({
    i: w.i,
    text: w.text,
    start_s: w.start,
    end_s: w.end,
    conf: w.conf,
    speaker: w.speaker,
  }))
}

export function utterancesFromRaw(doc: RawDoc): Utterance[] {
  return doc.utterances.map((u) => ({
    // Until the DB assigns real uuids, index-derived ids are stable within a document.
    id: `${doc.episode_id}:${u.i}`,
    i: u.i,
    speaker: u.speaker,
    start_s: u.start,
    end_s: u.end,
    text_asr: u.text,
    text_verified: null,
    verified_by: null,
    verified_at: null,
    text_readable: null,
    flags: [],
  }))
}

/** Clusters present in the transcript, unlabelled until a verifier names them. */
export function speakersFromRaw(doc: RawDoc): Speaker[] {
  const clusters = new Set<number>()
  doc.utterances.forEach((u) => clusters.add(u.speaker))
  doc.words.forEach((w) => clusters.add(w.speaker))
  return [...clusters].sort((a, b) => a - b).map((cluster) => ({ cluster, label: null }))
}

export function transcriptFromRaw(doc: RawDoc): Transcript {
  return {
    id: doc.episode_id,
    episode_id: doc.episode_id,
    engine: doc.engine.name,
    engine_version: doc.engine.sherpa_onnx_version ?? null,
    params: (doc.engine.params as Record<string, unknown>) ?? null,
    hotwords_sha256:
      (doc.engine.params?.hotwords_sha256 as string | undefined) ?? null,
    created_at: doc.created_at,
    speakers_pending: false,
    readable_available: false,
    words: wordsFromRaw(doc),
    utterances: utterancesFromRaw(doc),
    speakers: speakersFromRaw(doc),
  }
}

/** Word index -> utterance index, for highlighting and for click-to-play. */
export function wordToUtterance(doc: RawDoc): Map<number, number> {
  const map = new Map<number, number>()
  doc.utterances.forEach((u) => u.word_ids.forEach((id) => map.set(id, u.i)))
  return map
}
