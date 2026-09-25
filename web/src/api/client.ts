// Typed API client (PLAN §7, §9). Cookie auth — every request sends credentials.
// TODO(T4): generate from /api/openapi.json once the T3 handlers exist.

import type {
  Episode,
  EpisodeDetail,
  EpisodeListItem,
  GoogleRepo,
  Health,
  Hotword,
  HotwordSuggestion,
  Job,
  Me,
  Role,
  Stats,
  Transcript,
  User,
  Utterance,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`)
    this.name = 'ApiError'
  }

  /** True while an endpoint is still a T3 stub, so the UI can say so plainly. */
  get notImplemented(): boolean {
    return this.status === 501
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers:
      init.body instanceof FormData
        ? undefined
        : { 'Content-Type': 'application/json', ...init.headers },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const body = (value: unknown) => JSON.stringify(value)

export const api = {
  // --- ops ---------------------------------------------------------------
  health: () => request<Health>('/health'),
  stats: () => request<Stats>('/stats'),
  googleRepo: () => request<GoogleRepo>('/google-repo'),

  // --- auth --------------------------------------------------------------
  login: (username: string, password: string) =>
    request<Me>('/auth/login', { method: 'POST', body: body({ username, password }) }),
  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  me: () => request<Me>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>('/auth/password', {
      method: 'POST',
      body: body({ current_password, new_password }),
    }),

  // --- users (admin) -----------------------------------------------------
  listUsers: () => request<User[]>('/users'),
  createUser: (payload: { username: string; display_name?: string; role: Role; password: string }) =>
    request<User>('/users', { method: 'POST', body: body(payload) }),
  updateUser: (
    id: string,
    patch: Partial<{ display_name: string | null; role: Role; is_active: boolean; password: string }>,
  ) => request<User>(`/users/${id}`, { method: 'PATCH', body: body(patch) }),

  // --- episodes ----------------------------------------------------------
  listEpisodes: (params: { status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    )
    return request<EpisodeListItem[]>(`/episodes${qs.toString() ? `?${qs}` : ''}`)
  },
  getEpisode: (id: string) => request<EpisodeDetail>(`/episodes/${id}`),
  uploadEpisode: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Episode>('/episodes/upload', { method: 'POST', body: form })
  },
  episodeFromUrl: (payload: { url: string; title?: string; air_date?: string }) =>
    request<Episode>('/episodes/from-url', { method: 'POST', body: body(payload) }),
  transcribe: (id: string, params: Record<string, unknown> = {}) =>
    request<Job>(`/episodes/${id}/transcribe`, { method: 'POST', body: body(params) }),
  exportEpisode: (id: string) =>
    request<Job>(`/episodes/${id}/export`, { method: 'POST' }),
  deleteEpisode: (id: string) => request<void>(`/episodes/${id}`, { method: 'DELETE' }),

  // --- jobs --------------------------------------------------------------
  listJobs: (status?: string) =>
    request<Job[]>(`/jobs${status ? `?status=${status}` : ''}`),
  retryJob: (id: string) => request<Job>(`/jobs/${id}/retry`, { method: 'POST' }),
  jobLog: (id: string) => request<{ id: string; log: string }>(`/jobs/${id}/log`),

  // --- transcripts -------------------------------------------------------
  getTranscript: (id: string) => request<Transcript>(`/transcripts/${id}`),
  /** Bring the punctuated reading layer up to date (only changed passages are redone). */
  refreshReadable: (id: string) =>
    request<{ written: number }>(`/transcripts/${id}/readable`, { method: 'POST' }),
  audioUrl: (id: string) => `${BASE}/transcripts/${id}/audio`,
  /** Precomputed waveform; 404 when the server has no 16 kHz WAV to take it from. */
  getPeaks: (id: string) =>
    request<{ duration: number; peaks: number[] }>(`/transcripts/${id}/peaks`),

  // --- utterances --------------------------------------------------------
  // The payload is sent exactly as typed. No trim(), no normalisation — CLAUDE.md
  // rule 1 applies on this side of the wire too.
  patchUtterance: (
    id: string,
    patch: Partial<Pick<Utterance, 'text_verified' | 'flags'>> & {
      start_s?: number
      end_s?: number
    },
  ) => request<Utterance>(`/utterances/${id}`, { method: 'PATCH', body: body(patch) }),
  splitUtterance: (id: string, atWordI: number) =>
    request<Utterance[]>(`/utterances/${id}/split`, {
      method: 'POST',
      body: body({ at_word_i: atWordI }),
    }),
  mergeNext: (id: string) =>
    request<Utterance>(`/utterances/${id}/merge-next`, { method: 'POST' }),
  revertUtterance: (id: string) =>
    request<Utterance>(`/utterances/${id}/revert`, { method: 'POST' }),

  // --- hotwords ----------------------------------------------------------
  listHotwords: () => request<Hotword[]>('/hotwords'),
  hotwordSuggestions: () => request<HotwordSuggestion[]>('/hotwords/suggestions'),
  createHotword: (payload: { term: string; weight?: number; note?: string }) =>
    request<Hotword>('/hotwords', { method: 'POST', body: body(payload) }),
  patchHotword: (id: number, patch: Partial<Hotword>) =>
    request<Hotword>(`/hotwords/${id}`, { method: 'PATCH', body: body(patch) }),
  deleteHotword: (id: number) => request<void>(`/hotwords/${id}`, { method: 'DELETE' }),
  rerunAll: () => request<Job[]>('/hotwords/rerun-all', { method: 'POST' }),

  // --- exports -----------------------------------------------------------
  exportUrl: (episodeId: string, fmt: string) =>
    `${BASE}/episodes/${episodeId}/export.${fmt}`,
  allZipUrl: (fmt: string) => `${BASE}/exports/all.zip?fmt=${encodeURIComponent(fmt)}`,
}
