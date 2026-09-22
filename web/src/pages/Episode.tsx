// PLAN §10: "the Episode screen is the product".
//
// Layout: waveform + play controls pinned top; transcript below, grouped into
// utterances, each with a coloured speaker chip and a timestamp.
//
// Keyboard (PLAN §10):
//   Space   play/pause        [ / ]  previous / next utterance
//   L       loop utterance    Ctrl+Z revert utterance to text_asr
//
// Click a word → seek and play from that word. That single interaction is what makes
// verification 2x faster; everything else on this screen is secondary to it.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import ConfidenceToggle, { confPercentile } from '../components/ConfidenceToggle'
import SpeakerLegend from '../components/SpeakerLegend'
import TranscriptEditor from '../components/TranscriptEditor'
import WaveformPlayer, { type WaveformPlayerHandle } from '../components/WaveformPlayer'
import type { Utterance } from '../api/types'

const EXPORT_FORMATS = [
  { fmt: 'docx', label: 'Word (.docx)' },
  { fmt: 'txt', label: 'Text' },
  { fmt: 'verified.json', label: 'Verified JSON' },
  { fmt: 'json', label: 'Raw JSON' },
  { fmt: 'csv', label: 'Word CSV' },
  { fmt: 'srt', label: 'Subtitles' },
  { fmt: 'eaf', label: 'ELAN' },
]

export default function Episode() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const player = useRef<WaveformPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [showConf, setShowConf] = useState(false)
  const [percentile, setPercentile] = useState(15)
  const [activeIndex, setActiveIndex] = useState(0)

  const episode = useQuery({
    queryKey: ['episode', id],
    queryFn: () => api.getEpisode(id!),
    enabled: !!id,
    refetchInterval: (q) =>
      ['queued', 'processing'].includes(q.state.data?.status ?? '') ? 3000 : false,
  })

  const transcriptId = episode.data?.current_transcript_id ?? null

  const transcript = useQuery({
    queryKey: ['transcript', transcriptId],
    queryFn: () => api.getTranscript(transcriptId!),
    enabled: !!transcriptId,
  })

  const saveUtterance = useMutation({
    mutationFn: ({ utteranceId, text }: { utteranceId: string; text: string }) =>
      api.patchUtterance(utteranceId, { text_verified: text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] })
      queryClient.invalidateQueries({ queryKey: ['episode', id] })
    },
  })

  const revert = useMutation({
    mutationFn: (utteranceId: string) => api.revertUtterance(utteranceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] }),
  })

  const rename = useMutation({
    mutationFn: ({ cluster, label }: { cluster: number; label: string }) =>
      api.setSpeakerLabel(id!, cluster, label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] })
      queryClient.invalidateQueries({ queryKey: ['episode', id] })
    },
  })

  const transcribe = useMutation({
    mutationFn: () => api.transcribe(id!, { hotwords: true, diarize: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episode', id] }),
  })

  const utterances = transcript.data?.utterances ?? []
  const words = transcript.data?.words ?? []

  const speakerLabels = useMemo(() => {
    const map: Record<number, string> = {}
    for (const s of transcript.data?.speakers ?? []) if (s.label) map[s.cluster] = s.label
    return map
  }, [transcript.data])

  const confThreshold = useMemo(
    () => (showConf ? confPercentile(words, percentile) : null),
    [showConf, percentile, words],
  )

  // Highlight the utterance the playhead is inside.
  useEffect(() => {
    const i = utterances.findIndex(
      (u) => currentTime >= u.start_s && currentTime < u.end_s,
    )
    if (i >= 0) setActiveIndex(i)
  }, [currentTime, utterances])

  const seekTo = useCallback((seconds: number) => {
    player.current?.seekAndPlay(seconds)
  }, [])

  const goto = useCallback(
    (delta: number) => {
      const next = Math.max(0, Math.min(utterances.length - 1, activeIndex + delta))
      const u = utterances[next]
      if (u) {
        setActiveIndex(next)
        seekTo(u.start_s)
      }
    },
    [activeIndex, utterances, seekTo],
  )

  // Shortcuts are ignored while the caret is in an editable element, otherwise Space
  // would stop being a space.
  useEffect(() => {
    const isEditing = (t: EventTarget | null) => {
      const el = t as HTMLElement | null
      return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA'].includes(el.tagName))
    }
    const onKey = (e: KeyboardEvent) => {
      if (isEditing(e.target)) return
      if (e.key === ' ') {
        e.preventDefault()
        player.current?.playPause()
      } else if (e.key === '[') goto(-1)
      else if (e.key === ']') goto(1)
      else if (e.key === 'l' || e.key === 'L') {
        const u = utterances[activeIndex]
        if (u) player.current?.loop(u.start_s, u.end_s)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [goto, activeIndex, utterances])

  if (!id) return null
  if (episode.isLoading) return <p className="text-slate-500">Loading…</p>
  if (episode.isError) {
    return (
      <p className="text-rose-600">
        {episode.error instanceof ApiError ? episode.error.detail : 'Failed to load'}
      </p>
    )
  }

  const ep = episode.data!
  const verifiedCount = utterances.filter((u: Utterance) => u.text_verified !== null).length

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <Link to="/episodes" className="text-sm text-slate-500 hover:underline">
          ← Episodes
        </Link>
        <h1 className="text-xl font-semibold">{ep.title || ep.slug}</h1>
        <span className="text-sm text-slate-500">{ep.status}</span>
        {utterances.length > 0 && (
          <span className="text-sm text-slate-500">
            {verifiedCount} / {utterances.length} utterances verified
          </span>
        )}
      </header>

      {!transcriptId && (
        <div className="rounded border border-amber-200 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-900">No transcript yet.</p>
          <p className="mt-1 text-amber-800">
            {ep.status === 'queued' || ep.status === 'processing'
              ? 'A job is running — this page refreshes itself.'
              : 'Press Transcribe to queue this episode.'}
          </p>
          {ep.status !== 'queued' && ep.status !== 'processing' && (
            <button
              onClick={() => transcribe.mutate()}
              className="mt-3 rounded bg-slate-900 px-3 py-1.5 text-white"
            >
              Transcribe
            </button>
          )}
        </div>
      )}

      {transcriptId && (
        <>
          <WaveformPlayer
            ref={player}
            src={api.audioUrl(transcriptId)}
            onTimeUpdate={setCurrentTime}
          />

          <div className="flex flex-wrap items-center gap-4 rounded border border-slate-200 bg-white p-3">
            <SpeakerLegend
              speakers={transcript.data?.speakers ?? []}
              onRename={(cluster, label) => rename.mutate({ cluster, label })}
            />
            <div className="ml-auto flex items-center gap-4">
              <ConfidenceToggle
                enabled={showConf}
                onChange={setShowConf}
                percentile={percentile}
                onPercentileChange={setPercentile}
                threshold={confThreshold}
              />
              <div className="flex gap-1">
                {EXPORT_FORMATS.map((f) => (
                  <a
                    key={f.fmt}
                    href={api.exportUrl(id, f.fmt)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                  >
                    {f.label}
                  </a>
                ))}
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-400">
            Click a word to play from it. Space play/pause · [ ] previous/next · L loop.
            Text is stored exactly as typed — no spellcheck, no autocorrect.
          </p>

          {transcript.isLoading ? (
            <p className="text-slate-500">Loading transcript…</p>
          ) : (
            <TranscriptEditor
              utterances={utterances}
              words={words}
              speakerLabels={speakerLabels}
              onWordClick={(w) => seekTo(w.start_s)}
              onSave={(utteranceId, text) => saveUtterance.mutate({ utteranceId, text })}
              onRevert={(utteranceId) => revert.mutate(utteranceId)}
              confThreshold={confThreshold}
              activeIndex={activeIndex}
              onActivate={setActiveIndex}
            />
          )}
        </>
      )}
    </section>
  )
}
