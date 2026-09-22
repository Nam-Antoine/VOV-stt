// PLAN §10: status chips, bulk "enqueue all ingested", upload dropzone, URL box.
//
// The primary flow is one gesture: drop audio, get a transcript. Uploading used to
// only stage the file and wait for a second click on Transcribe; that click is now
// automatic (and switchable off for a bulk ingest you want to queue deliberately).
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { Search, Spinner, Upload } from '../components/Icons'
import type { EpisodeListItem, EpisodeStatus, Job } from '../api/types'

const STATUS_STYLE: Record<EpisodeStatus, string> = {
  ingested: 'bg-sunken text-muted',
  queued: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  processing: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  transcribed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  verifying: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300',
  verified: 'bg-emerald-600 text-white',
  failed: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

const IN_FLIGHT = ['queued', 'processing']

/** Measured on this box: 846 s of audio in ~166 s wall clock, diarization included. */
const REALTIME_FACTOR = 5.1

const AUTO_KEY = 'vnstt.autoTranscribe'

export function StatusChip({ status }: { status: EpisodeStatus }) {
  return <span className={`chip ${STATUS_STYLE[status] ?? ''}`}>{status}</span>
}

function duration(seconds: number | null) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function humanEta(seconds: number) {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s left`
  return `${Math.round(seconds / 60)} min left`
}

/**
 * A progress estimate, clearly an estimate. There is no per-episode progress on the
 * wire — the pipeline reports nothing until it is finished — so this is elapsed time
 * against the measured realtime factor. It never reaches 100%: the bar is there to
 * show the job is alive and roughly how long is left, not to promise a completion.
 */
function Progress({ episode, job, now }: {
  episode: EpisodeListItem
  job: Job | undefined
  now: number
}) {
  if (!IN_FLIGHT.includes(episode.status)) return null

  const startedAt = job?.started_at ? Date.parse(job.started_at) : null
  const expected = episode.duration_s ? episode.duration_s / REALTIME_FACTOR : null

  if (episode.status === 'queued' || !startedAt || !expected) {
    return (
      <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
        <Spinner className="h-3 w-3" />
        {episode.status === 'queued' ? 'waiting for the worker' : 'transcribing'}
      </div>
    )
  }

  const elapsed = (now - startedAt) / 1000
  const fraction = Math.min(0.95, elapsed / expected)
  const remaining = Math.max(0, expected - elapsed)

  return (
    <div className="mt-1.5 max-w-xs">
      <div className="h-1 overflow-hidden rounded-full bg-sunken">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear"
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <div className="mt-1 text-xs tabular-nums text-muted">
        transcribing · ~{humanEta(remaining)}
      </div>
    </div>
  )
}

export default function Episodes() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [dragging, setDragging] = useState(false)
  const [auto, setAuto] = useState(() => localStorage.getItem(AUTO_KEY) !== 'off')
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    localStorage.setItem(AUTO_KEY, auto ? 'on' : 'off')
  }, [auto])

  // Typing should not fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQ(search), 250)
    return () => clearTimeout(t)
  }, [search])

  const episodes = useQuery({
    queryKey: ['episodes', q],
    queryFn: () => api.listEpisodes(q ? { q } : {}),
    // While anything is mid-flight the list is the progress indicator.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((e: EpisodeListItem) => IN_FLIGHT.includes(e.status))
        ? 3000
        : false,
  })

  const rows = useMemo(() => episodes.data ?? [], [episodes.data])
  const busy = rows.some((e) => IN_FLIGHT.includes(e.status))

  // Jobs carry started_at, which is what turns "processing" into an ETA.
  const jobs = useQuery({
    queryKey: ['jobs', 'running'],
    queryFn: () => api.listJobs(),
    enabled: busy,
    refetchInterval: busy ? 3000 : false,
  })

  const jobByEpisode = useMemo(() => {
    const map = new Map<string, Job>()
    for (const j of jobs.data ?? []) {
      if (j.kind !== 'transcribe' || !j.episode_id) continue
      if (!['queued', 'running'].includes(j.status)) continue
      map.set(j.episode_id, j)
    }
    return map
  }, [jobs.data])

  // The ETA needs a clock of its own; the list only refetches every 3 s.
  useEffect(() => {
    if (!busy) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [busy])

  const transcribe = useMutation({
    mutationFn: (id: string) => api.transcribe(id, { hotwords: true, diarize: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episodes'] }),
  })

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const file of Array.from(files)) {
        const episode = await api.uploadEpisode(file)
        // One gesture: the file the operator just dropped is the file they want read.
        //
        // Upload dedupes on sha256 and hands back the EXISTING episode for a repeat
        // file, which may already be transcribed. Re-queueing that would spend ~3
        // minutes of a shared 4-vCPU box re-deriving a transcript we already have,
        // so only episodes actually waiting for one are queued.
        const waiting = episode.status === 'ingested' || episode.status === 'failed'
        if (auto && waiting) {
          await api.transcribe(episode.id, { hotwords: true, diarize: true })
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const ingested = rows.filter((e) => e.status === 'ingested')

  return (
    <section>
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Episodes</h1>
        {rows.length > 0 && (
          <span className="text-sm text-faint">{rows.length}</span>
        )}

        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or slug"
            aria-label="Search episodes"
            className="field w-56 pl-8"
          />
        </div>

        {ingested.length > 0 && (
          <button
            onClick={() => ingested.forEach((e) => transcribe.mutate(e.id))}
            className="btn-outline"
          >
            Transcribe {ingested.length} waiting
          </button>
        )}
      </header>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (e.dataTransfer.files.length) upload.mutate(e.dataTransfer.files)
        }}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            fileInput.current?.click()
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload episode audio"
        className={`mb-5 cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
          dragging
            ? 'border-accent bg-accent/5'
            : 'border-line bg-surface hover:border-accent/50'
        }`}
      >
        <input
          ref={fileInput}
          type="file"
          accept="audio/*,video/mp4,.m4a,.mp3,.wav,.webm"
          multiple
          hidden
          onChange={(e) => e.target.files && upload.mutate(e.target.files)}
        />
        {upload.isPending ? (
          <div className="flex items-center justify-center gap-2 text-sm text-muted">
            <Spinner className="h-4 w-4" />
            Uploading…
          </div>
        ) : (
          <>
            <Upload className="mx-auto h-6 w-6 text-faint" />
            <p className="mt-2 text-sm font-medium">
              Drop audio here, or click to choose
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {auto
                ? 'Transcription starts automatically.'
                : 'Files are staged; press Transcribe when you are ready.'}
              {' '}mp3 · m4a · wav · webm · mp4
            </p>
          </>
        )}
      </div>

      <label
        className="mb-5 flex cursor-pointer items-center gap-2 text-xs text-muted"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={auto}
          onChange={(e) => setAuto(e.target.checked)}
          className="accent-accent"
        />
        Start transcribing as soon as a file finishes uploading
      </label>

      {upload.isError && (
        <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          {upload.error instanceof ApiError ? upload.error.detail : 'Upload failed'}
        </p>
      )}

      {/* Mobile: cards. A five-column table at 375 px is unreadable. */}
      <ul className="space-y-2 sm:hidden">
        {rows.map((e) => (
          <li key={e.id} className="card p-3">
            <div className="flex items-start gap-2">
              <Link to={`/episodes/${e.id}`} className="min-w-0 flex-1 font-medium">
                <span className="block truncate">{e.title || e.slug}</span>
                <span className="block truncate text-xs text-faint">{e.slug}</span>
              </Link>
              <StatusChip status={e.status} />
            </div>
            <Progress episode={e} job={jobByEpisode.get(e.id)} now={now} />
            <div className="mt-2 flex items-center gap-3 text-xs text-muted">
              <span className="tabular-nums">{duration(e.duration_s)}</span>
              {e.n_utterances > 0 && (
                <span className="tabular-nums">
                  {e.n_verified}/{e.n_utterances} verified
                </span>
              )}
              <span className="ml-auto">
                {e.status === 'ingested' || e.status === 'failed' ? (
                  <button
                    onClick={() => transcribe.mutate(e.id)}
                    className="btn-outline btn-sm"
                  >
                    Transcribe
                  </button>
                ) : e.current_transcript_id ? (
                  <Link to={`/episodes/${e.id}`} className="btn-outline btn-sm">
                    Open
                  </Link>
                ) : null}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-hidden rounded-xl border border-line bg-surface sm:block">
        <table className="w-full text-sm">
          <thead className="bg-sunken text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">Episode</th>
              <th className="px-4 py-2.5 font-medium">Length</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Verified</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr
                key={e.id}
                className="border-t border-line transition-colors hover:bg-sunken/50"
              >
                <td className="px-4 py-3">
                  <Link
                    to={`/episodes/${e.id}`}
                    className="font-medium hover:text-accent hover:underline"
                  >
                    {e.title || e.slug}
                  </Link>
                  <div className="text-xs text-faint">{e.slug}</div>
                  <Progress episode={e} job={jobByEpisode.get(e.id)} now={now} />
                </td>
                <td className="px-4 py-3 align-top tabular-nums text-muted">
                  {duration(e.duration_s)}
                </td>
                <td className="px-4 py-3 align-top">
                  <StatusChip status={e.status} />
                </td>
                <td className="px-4 py-3 align-top tabular-nums text-muted">
                  {e.n_utterances ? `${e.n_verified} / ${e.n_utterances}` : '—'}
                </td>
                <td className="px-4 py-3 text-right align-top">
                  {e.status === 'ingested' || e.status === 'failed' ? (
                    <button
                      onClick={() => transcribe.mutate(e.id)}
                      className="btn-outline btn-sm"
                    >
                      Transcribe
                    </button>
                  ) : e.current_transcript_id ? (
                    <Link to={`/episodes/${e.id}`} className="btn-outline btn-sm">
                      Open
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-muted">
                  {episodes.isLoading
                    ? 'Loading…'
                    : q
                      ? `Nothing matches “${q}”.`
                      : 'No episodes yet — drop an audio file above.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && !episodes.isLoading && (
        <p className="py-8 text-center text-sm text-muted sm:hidden">
          {q ? `Nothing matches “${q}”.` : 'No episodes yet — drop an audio file above.'}
        </p>
      )}
    </section>
  )
}
