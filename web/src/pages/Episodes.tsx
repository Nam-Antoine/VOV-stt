// PLAN §10: status chips, bulk "enqueue all ingested", upload dropzone, URL box.
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { EpisodeListItem, EpisodeStatus } from '../api/types'

const STATUS_STYLE: Record<EpisodeStatus, string> = {
  ingested: 'bg-slate-100 text-slate-700',
  queued: 'bg-amber-100 text-amber-800',
  processing: 'bg-blue-100 text-blue-800',
  transcribed: 'bg-emerald-100 text-emerald-800',
  verifying: 'bg-indigo-100 text-indigo-800',
  verified: 'bg-emerald-600 text-white',
  failed: 'bg-rose-100 text-rose-800',
}

function StatusChip({ status }: { status: EpisodeStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[status] ?? ''}`}>
      {status}
    </span>
  )
}

function duration(seconds: number | null) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function Episodes() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [q, setQ] = useState('')
  const [dragging, setDragging] = useState(false)

  const episodes = useQuery({
    queryKey: ['episodes', q],
    queryFn: () => api.listEpisodes(q ? { q } : {}),
    // While anything is mid-flight the list is the progress indicator.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((e: EpisodeListItem) =>
        ['queued', 'processing'].includes(e.status),
      )
        ? 3000
        : false,
  })

  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const file of Array.from(files)) await api.uploadEpisode(file)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episodes'] }),
  })

  const transcribe = useMutation({
    mutationFn: (id: string) => api.transcribe(id, { hotwords: true, diarize: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episodes'] }),
  })

  const rows = episodes.data ?? []
  const ingested = rows.filter((e) => e.status === 'ingested')

  return (
    <section>
      <header className="mb-4 flex items-center gap-3">
        <h1 className="text-xl font-semibold">Episodes</h1>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search title or slug"
          className="ml-auto rounded border border-slate-300 px-3 py-1.5 text-sm"
        />
        {ingested.length > 0 && (
          <button
            onClick={() => ingested.forEach((e) => transcribe.mutate(e.id))}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          >
            Transcribe all {ingested.length} ingested
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
        className={`mb-5 cursor-pointer rounded border-2 border-dashed p-6 text-center text-sm ${
          dragging ? 'border-slate-900 bg-slate-100' : 'border-slate-300 bg-white'
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
          <span>Uploading…</span>
        ) : (
          <span className="text-slate-600">
            Drop episode audio here, or click to choose. Nothing is transcribed until you
            press <b>Transcribe</b>.
          </span>
        )}
      </div>

      {upload.isError && (
        <p className="mb-4 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {upload.error instanceof ApiError ? upload.error.detail : 'Upload failed'}
        </p>
      )}

      <div className="overflow-hidden rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Episode</th>
              <th className="px-3 py-2">Length</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Verified</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <Link to={`/episodes/${e.id}`} className="font-medium hover:underline">
                    {e.title || e.slug}
                  </Link>
                  <div className="text-xs text-slate-400">{e.slug}</div>
                </td>
                <td className="px-3 py-2 tabular-nums">{duration(e.duration_s)}</td>
                <td className="px-3 py-2">
                  <StatusChip status={e.status} />
                </td>
                <td className="px-3 py-2 tabular-nums text-slate-600">
                  {e.n_utterances ? `${e.n_verified} / ${e.n_utterances}` : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  {e.status === 'ingested' || e.status === 'failed' ? (
                    <button
                      onClick={() => transcribe.mutate(e.id)}
                      className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      Transcribe
                    </button>
                  ) : e.current_transcript_id ? (
                    <Link
                      to={`/episodes/${e.id}`}
                      className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      Open
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-400">
                  {episodes.isLoading ? 'Loading…' : 'No episodes yet — upload one above.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
