// Mirrors backend/app/schemas.py (PLAN §9).
// TODO(T4): generate this from /api/openapi.json instead of hand-maintaining it.

export type EpisodeStatus =
  | 'ingested'
  | 'queued'
  | 'processing'
  | 'transcribed'
  | 'verifying'
  | 'verified'
  | 'failed'

export type JobKind = 'transcribe' | 'export' | 'google_sync'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed'

export interface Episode {
  id: string
  slug: string
  title: string | null
  source_url: string | null
  air_date: string | null
  audio_path: string | null
  audio_sha256: string | null
  duration_s: number | null
  status: EpisodeStatus
  created_at: string
  updated_at: string
}

export interface EpisodeListItem extends Episode {
  current_transcript_id: string | null
  n_utterances: number
  n_verified: number
}

export interface EpisodeDetail extends Episode {
  current_transcript_id: string | null
  n_utterances: number
  n_verified: number
  n_words: number
}

export interface Word {
  i: number
  text: string
  start_s: number
  end_s: number | null
  /** Mean log-prob; lower is worse. null when the runtime gave no logprobs. */
  conf: number | null
}

export interface Utterance {
  id: string
  i: number
  start_s: number
  end_s: number
  /** Frozen engine output. Never edited. */
  text_asr: string
  /** null = untouched. '' is a deliberate edit ("no speech here"). */
  text_verified: string | null
  verified_by: string | null
  verified_at: string | null
  flags: string[]
  /** Punctuated, cased reading of the current text. Derived — never corpus text.
   *  null = not computed yet, or stale after an edit. */
  text_readable: string | null
}

export interface Transcript {
  id: string
  episode_id: string
  engine: string
  engine_version: string | null
  params: Record<string, unknown> | null
  hotwords_sha256: string | null
  created_at: string
  words: Word[]
  utterances: Utterance[]
  /** The punctuation model is installed on the server. */
  readable_available: boolean
}

/** The Google Sheet + Docs repository (read-only here). */
export interface GoogleRepo {
  enabled: boolean
  sheet_url: string | null
  /** ISO time of the last full sync, UTC. */
  last_full_sync: string | null
}

export interface Job {
  id: string
  episode_id: string | null
  episode_title: string | null
  kind: JobKind
  status: JobStatus
  attempts: number
  max_attempts: number
  params: Record<string, unknown> | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Hotword {
  id: number
  term: string
  weight: number
  note: string | null
  active: boolean
  created_at: string
}

/** A phrase verifiers corrected, offered as a hotword (the model can't be fine-tuned). */
export interface HotwordSuggestion {
  term: string
  count: number
  examples: { episode_id: string; title: string; heard: string; corrected: string }[]
}

export interface Stats {
  episodes_by_status: Record<string, number>
  hours_transcribed: number
  hours_verified: number
  mean_conf: number | null
}

export interface Health {
  ok: boolean
  db: boolean
  models: Record<string, boolean>
  worker_heartbeat_s: number | null
  version: string
  readable_available: boolean
  /** disabled | ok | token_invalid | error: <reason> */
  google_repo: string
}

export const UTTERANCE_FLAGS = ['overlap', 'unclear', 'music', 'not-speech'] as const
export type UtteranceFlag = (typeof UTTERANCE_FLAGS)[number]

/** The text a verifier sees: their own if they have typed one, else the engine's. */
export function displayText(u: Utterance): string {
  return u.text_verified !== null ? u.text_verified : u.text_asr
}

export type Role = 'admin' | 'editor'

/** The signed-in account (GET /auth/me). */
export interface Me {
  username: string
  display_name: string | null
  role: Role
  /** False: the site has no login (the default deployment). */
  auth_enabled: boolean
}

export interface User extends Me {
  id: string
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
}
