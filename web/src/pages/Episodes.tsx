// PLAN §10: status chips, bulk "enqueue all ingested", upload dropzone, URL box.
//
// The primary flow is one gesture: drop audio, get a transcript. Uploading used to
// only stage the file and wait for a second click on Transcribe; that click is now
// automatic (and switchable off for a bulk ingest you want to queue deliberately).
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { CloudUpload, Cycle, Play, Search, Spinner, Waveform } from '../components/Icons'
import type { Episode, EpisodeListItem, EpisodeStatus, Job } from '../api/types'
import { EPISODE_STATUS_LABEL } from '../labels'

// Earthy, low-chroma chips: status is read at a glance but should not out-shout the
// episode titles. Only `verified` is filled — it is the finish line.
const STATUS_STYLE: Record<EpisodeStatus, string> = {
  ingested: 'bg-sunken text-muted',
  queued: 'bg-[#f1e4c8] text-[#7a5a12] dark:bg-[#3a2f18] dark:text-[#e3c27a]',
  processing: 'bg-[#dbe7ef] text-[#2c5d7c] dark:bg-[#1c2c36] dark:text-[#9cc3dc]',
  transcribed: 'bg-[#e1ead8] text-[#40652d] dark:bg-[#23301c] dark:text-[#a9cc94]',
  verifying: 'bg-[#efdcd2] text-[#8a4b2a] dark:bg-[#3a261b] dark:text-[#e8b490]',
  verified: 'bg-verified text-[#fbf9f4]',
  failed: 'bg-[#f3dcd3] text-[#8a2d17] dark:bg-[#3a1f17] dark:text-[#f0b39c]',
}

const IN_FLIGHT = ['queued', 'processing']

/** Measured on this box: 846 s of audio in ~166 s wall clock, diarization included. */
const REALTIME_FACTOR = 5.1

const AUTO_KEY = 'vnstt.autoTranscribe'

/** The server's cap; checked here too so a huge file is skipped before it is sent. */
const MAX_UPLOAD_BYTES = 512 * 1024 * 1024

export function StatusChip({
  status,
  speakersPending = false,
}: {
  status: EpisodeStatus
  /** Text is readable already; only the speaker labels are still being worked out. */
  speakersPending?: boolean
}) {
  return (
    <span className={`chip ${STATUS_STYLE[status] ?? ''}`}>
      {(status === 'queued' || status === 'processing') && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
      )}
      {speakersPending ? 'Đã có văn bản' : (EPISODE_STATUS_LABEL[status] ?? status)}
    </span>
  )
}

/** Transcribe what is waiting (or failed); open what has a transcript. */
function RowAction({ episode, onTranscribe }: { episode: EpisodeListItem; onTranscribe: () => void }) {
  if (episode.status === 'ingested' || episode.status === 'failed') {
    return (
      <button onClick={onTranscribe} className="btn-outline btn-sm">
        Chép lời
      </button>
    )
  }
  if (!episode.current_transcript_id) return null
  return (
    <Link to={`/episodes/${episode.id}`} className="btn-outline btn-sm">
      Mở
    </Link>
  )
}

function duration(seconds: number | null) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function humanEta(seconds: number) {
  if (seconds < 60) return `còn ${Math.max(1, Math.round(seconds))} giây`
  return `còn ${Math.round(seconds / 60)} phút`
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
        {episode.status === 'queued' ? 'đang chờ xử lý' : 'đang chép lời'}
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
          className="h-full rounded-full bg-accent-strong transition-[width] duration-1000 ease-linear"
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <div className="mt-1 text-xs tabular-nums text-muted">
        đang chép lời · ~{humanEta(remaining)}
      </div>
    </div>
  )
}

const STEPS = [
  { Icon: CloudUpload, label: 'Tải file âm thanh lên' },
  { Icon: Cycle, label: 'Chờ hệ thống chép lời xong' },
  { Icon: Waveform, label: 'Nghe, sửa và duyệt bản chép lời' },
]

/** The reference's "three steps" strip. The step the operator is on is filled lime. */
function Steps({ current }: { current: number }) {
  return (
    <div className="card px-4 py-6 sm:px-8">
      <h2 className="text-center text-lg font-medium sm:text-xl">Chép lời trong ba bước</h2>
      <ol className="mx-auto mt-6 grid max-w-3xl gap-4 sm:grid-cols-3 sm:gap-0">
        {STEPS.map(({ Icon, label }, i) => (
          <li key={label} className="relative flex items-center gap-3 sm:flex-col sm:gap-3 sm:text-center">
            {/* Connector to the next step, drawn from this badge's centre. */}
            {i < STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className="absolute left-[calc(50%+2.25rem)] right-[calc(-50%+2.25rem)] top-6 hidden h-px bg-line sm:block"
              />
            )}
            <span
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-colors ${
                i === current ? 'bg-accent text-accent-ink' : 'bg-sunken text-faint'
              }`}
            >
              <Icon className="h-5 w-5" />
            </span>
            <span className={`text-sm ${i === current ? 'font-medium text-ink' : 'text-muted'}`}>
              {label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Under the title: the air date when known (VOV episodes), else the file's slug. */
function subtitle(e: { air_date: string | null; slug: string }) {
  if (!e.air_date) return e.slug
  const [y, m, d] = e.air_date.split('-')
  return `Phát sóng ${d}/${m}/${y}`
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

  // Which file of the batch is on the wire, for "Đang tải lên 3/10".
  const [progress, setProgress] = useState<{ index: number; total: number; name: string } | null>(null)

  const upload = useMutation({
    mutationFn: async (fileList: FileList) => {
      // A fresh upload always comes back `ingested`; anything else is an episode that
      // already existed. Collected so the operator is told, not left staring at a
      // list that did not change.
      const repeats: Episode[] = []
      // One bad file must not sink the batch: it is noted and the rest carry on.
      const failures: { name: string; reason: string }[] = []
      const files = Array.from(fileList)
      for (const [i, file] of files.entries()) {
        setProgress({ index: i + 1, total: files.length, name: file.name })
        if (file.size > MAX_UPLOAD_BYTES) {
          failures.push({ name: file.name, reason: 'lớn hơn 512 MB' })
          continue
        }
        let episode: Episode
        try {
          episode = await api.uploadEpisode(file)
        } catch (err) {
          failures.push({ name: file.name, reason: err instanceof ApiError ? err.detail : 'tải lên thất bại' })
          continue
        }
        // One gesture: the file the operator just dropped is the file they want read.
        //
        // Upload dedupes on sha256 and hands back the EXISTING episode for a repeat
        // file, which may already be transcribed. Re-queueing that would spend ~3
        // minutes of a shared 4-vCPU box re-deriving a transcript we already have,
        // so only episodes actually waiting for one are queued.
        const waiting = episode.status === 'ingested' || episode.status === 'failed'
        const queued = auto && waiting
        if (queued) {
          try {
            await api.transcribe(episode.id, { hotwords: true, diarize: true })
          } catch (err) {
            failures.push({
              name: file.name,
              reason: `đã tải lên nhưng chưa xếp hàng chép lời (${err instanceof ApiError ? err.detail : 'lỗi'})`,
            })
          }
        }
        if (episode.status !== 'ingested' && !queued) repeats.push(episode)
        // Each finished file shows up in the library straight away, not at the end.
        queryClient.invalidateQueries({ queryKey: ['episodes'] })
      }
      return { repeats, failures, total: files.length }
    },
    onSettled: () => {
      setProgress(null)
      if (fileInput.current) fileInput.current.value = ''
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const ingested = rows.filter((e) => e.status === 'ingested')
  const emptyText = q ? `Không có kết quả cho “${q}”.` : 'Chưa có tập nào — hãy thả file âm thanh vào ô phía trên.'

  return (
    <section>
      <input
        ref={fileInput}
        type="file"
        accept="audio/*,video/mp4,.m4a,.mp3,.wav,.webm"
        multiple
        hidden
        onChange={(e) => e.target.files && upload.mutate(e.target.files)}
      />

      <header className="mb-5 flex flex-wrap items-center gap-3">
        <div>
          <p className="eyebrow">Kho ngữ liệu</p>
          <h1 className="title mt-1">Tải lên và chép lời</h1>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:ml-auto sm:w-auto">
          {ingested.length > 0 && (
            <button
              onClick={() => ingested.forEach((e) => transcribe.mutate(e.id))}
              className="btn-outline"
            >
              Chép lời {ingested.length} tập đang chờ
            </button>
          )}
        </div>
      </header>

      <Steps current={upload.isPending ? 0 : busy ? 1 : rows.some((e) => e.current_transcript_id) ? 2 : 0} />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (upload.isPending) return
          if (e.dataTransfer.files.length) upload.mutate(e.dataTransfer.files)
        }}
        onClick={() => !upload.isPending && fileInput.current?.click()}
        onKeyDown={(e) => {
          if (upload.isPending) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            fileInput.current?.click()
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Tải lên âm thanh"
        aria-disabled={upload.isPending}
        className={`mb-3 mt-4 flex min-h-[18rem] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-strong sm:min-h-[22rem] ${
          dragging
            ? 'border-accent-strong bg-accent/15'
            : 'border-line bg-sunken hover:border-faint'
        }`}
      >
        {upload.isPending ? (
          <div className="flex items-center justify-center gap-2 text-base text-muted">
            <Spinner className="h-5 w-5" />
            <span className="min-w-0">
              <span className="block">
                {progress && progress.total > 1
                  ? `Đang tải lên ${progress.index}/${progress.total}…`
                  : 'Đang tải lên…'}
              </span>
              {progress && (
                <span className="mt-1 block max-w-md truncate text-xs text-faint">{progress.name}</span>
              )}
            </span>
          </div>
        ) : (
          <>
            <CloudUpload className="h-16 w-16 text-faint sm:h-20 sm:w-20" />
            <p className="mt-5 max-w-lg text-lg leading-snug sm:text-xl">
              Kéo thả hoặc <b className="font-semibold">CHỌN</b> một hoặc nhiều file âm thanh để tải lên
            </p>
            <p className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm text-muted">
              <span>Có thể tải lên:</span>
              <span className="inline-flex items-center gap-1.5 text-ink">
                <Waveform className="h-4 w-4 text-faint" /> MP3, M4A, WAV
              </span>
              <span className="inline-flex items-center gap-1.5 text-ink">
                <Play className="h-3.5 w-3.5 text-faint" /> MP4, WEBM
              </span>
            </p>
            <p className="mt-2 text-xs text-faint">
              (tối đa 512 MB mỗi file ·{' '}
              {auto
                ? 'chép lời sẽ tự động bắt đầu'
                : 'file được lưu chờ, bấm Chép lời khi bạn sẵn sàng'}
              )
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
        />
        Tự động chép lời ngay khi tải file lên xong
      </label>

      {upload.isSuccess && upload.data.failures.length > 0 && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300" role="alert">
          <p className="font-medium">
            {upload.data.failures.length}/{upload.data.total} file không tải lên được
            {upload.data.failures.length < upload.data.total ? ' — các file còn lại vẫn tải lên bình thường' : ''}:
          </p>
          <ul className="mt-1 list-disc pl-5">
            {upload.data.failures.map((f, i) => (
              <li key={i}>
                <span className="break-all font-medium">{f.name}</span>: {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {upload.isSuccess && upload.data.repeats.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {upload.data.repeats.map((e) => (
            <p key={e.id}>
              File âm thanh này đã được tải lên trước đó với tên{' '}
              <Link to={`/episodes/${e.id}`} className="font-medium underline">
                {e.title || e.slug}
              </Link>{' '}
              ({EPISODE_STATUS_LABEL[e.status] ?? e.status}). Không có tác vụ mới nào được thêm.
            </p>
          ))}
        </div>
      )}

      {upload.isError && (
        <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          Tải lên bị gián đoạn — hãy thử lại.
        </p>
      )}

      {/* Mobile: cards. A five-column table at 375 px is unreadable. */}
      <div className="mb-3 mt-10 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">
          Thư viện
          {rows.length > 0 && (
            <span className="ml-2 text-sm font-normal tabular-nums text-faint">{rows.length}</span>
          )}
        </h2>
        <div className="relative w-full sm:ml-auto sm:w-auto">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Tìm theo tên hoặc mã tập"
            aria-label="Tìm tập"
            className="field w-full pl-8 sm:w-64"
          />
        </div>
      </div>
      <ul className="divide-y divide-line border-y border-line sm:hidden">
        {rows.map((e) => (
          <li key={e.id} className="py-3">
            <div className="flex items-start gap-2">
              <Link to={`/episodes/${e.id}`} className="min-w-0 flex-1 font-reading text-base font-medium">
                <span className="block truncate">{e.title || e.slug}</span>
                <span className="block truncate font-sans text-xs font-normal text-faint">{subtitle(e)}</span>
              </Link>
              <StatusChip status={e.status} speakersPending={e.speakers_pending} />
            </div>
            <Progress episode={e} job={jobByEpisode.get(e.id)} now={now} />
            <div className="mt-2 flex items-center gap-3 text-xs text-muted">
              <span className="tabular-nums">{duration(e.duration_s)}</span>
              {e.n_utterances > 0 && (
                <span className="tabular-nums">
                  {e.n_verified}/{e.n_utterances} đã duyệt
                </span>
              )}
              <span className="ml-auto">
                <RowAction episode={e} onTranscribe={() => transcribe.mutate(e.id)} />
              </span>
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden border-t border-line sm:block">
        <table className="w-full text-sm">
          <thead className="whitespace-nowrap text-left text-[0.6875rem] uppercase tracking-[0.14em] text-faint">
            <tr>
              <th className="py-3 pr-4 font-semibold">Tập</th>
              <th className="py-3 pr-4 font-semibold">Thời lượng</th>
              <th className="py-3 pr-4 font-semibold">Trạng thái</th>
              <th className="py-3 pr-4 font-semibold">Đã duyệt</th>
              <th className="py-3" />
            </tr>
          </thead>
          <tbody className="border-b border-line">
            {rows.map((e) => (
              <tr
                key={e.id}
                className="border-t border-line transition-colors hover:bg-sunken/60"
              >
                <td className="py-4 pr-4">
                  <Link
                    to={`/episodes/${e.id}`}
                    className="font-reading text-base font-medium hover:text-accent-strong"
                  >
                    {e.title || e.slug}
                  </Link>
                  <div className="text-xs text-faint">{subtitle(e)}</div>
                  <Progress episode={e} job={jobByEpisode.get(e.id)} now={now} />
                </td>
                <td className="py-4 pr-4 align-top tabular-nums text-muted">
                  {duration(e.duration_s)}
                </td>
                <td className="py-4 pr-4 align-top">
                  <StatusChip status={e.status} speakersPending={e.speakers_pending} />
                </td>
                <td className="py-4 pr-4 align-top tabular-nums text-muted">
                  {e.n_utterances ? `${e.n_verified} / ${e.n_utterances}` : '—'}
                </td>
                <td className="py-4 pr-4 text-right align-top">
                  <RowAction episode={e} onTranscribe={() => transcribe.mutate(e.id)} />
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-muted">
                  {episodes.isLoading ? 'Đang tải…' : emptyText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && !episodes.isLoading && (
        <p className="py-8 text-center text-sm text-muted sm:hidden">
          {emptyText}
        </p>
      )}
    </section>
  )
}
