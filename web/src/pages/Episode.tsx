// PLAN §10: "the Episode screen is the product".
//
// Layout: waveform pinned under the app header; transcript below, one card per
// utterance with a coloured speaker rule down its left edge.
//
// Keyboard (PLAN §10, plus F and ? added here):
//   Space  play/pause     [ / ]  previous / next utterance
//   L      loop utterance F      follow the playhead      ?  shortcut list
//
// Click a word → seek and play from that word. That single interaction is what makes
// verification 2x faster; everything else on this screen is secondary to it.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import ConfidenceToggle, { confPercentile } from '../components/ConfidenceToggle'
import ExportMenu from '../components/ExportMenu'
import { Spinner } from '../components/Icons'
import Shortcuts from '../components/Shortcuts'
import SpeakerLegend from '../components/SpeakerLegend'
import TranscriptEditor from '../components/TranscriptEditor'
import WaveformPlayer, { type WaveformPlayerHandle } from '../components/WaveformPlayer'
import type { Utterance } from '../api/types'

export default function Episode() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const player = useRef<WaveformPlayerHandle>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [showConf, setShowConf] = useState(false)
  const [percentile, setPercentile] = useState(15)
  const [activeIndex, setActiveIndex] = useState(0)
  const [follow, setFollow] = useState(true)
  const [showKeys, setShowKeys] = useState(false)

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

  const utterances = useMemo(
    () => transcript.data?.utterances ?? [],
    [transcript.data],
  )
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
      } else if (e.key === 'f' || e.key === 'F') setFollow((v) => !v)
      else if (e.key === '?') setShowKeys(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [goto, activeIndex, utterances])

  if (!id) return null
  if (episode.isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted">
        <Spinner className="h-4 w-4" /> Loading…
      </div>
    )
  }
  if (episode.isError) {
    return (
      <p className="text-rose-600">
        {episode.error instanceof ApiError ? episode.error.detail : 'Failed to load'}
      </p>
    )
  }

  const ep = episode.data!
  const verifiedCount = utterances.filter((u: Utterance) => u.text_verified !== null).length
  const pct = utterances.length ? (verifiedCount / utterances.length) * 100 : 0

  return (
    <section className="space-y-4">
      {showKeys && <Shortcuts onClose={() => setShowKeys(false)} />}

      <header>
        <Link to="/episodes" className="text-sm text-muted hover:text-ink">
          ← Episodes
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-xl font-semibold">{ep.title || ep.slug}</h1>
          <span className="text-sm text-faint">{ep.status}</span>
          {utterances.length > 0 && (
            <span className="ml-auto flex items-center gap-2 text-sm text-muted">
              <span className="tabular-nums">
                {verifiedCount} / {utterances.length} verified
              </span>
              <span className="h-1.5 w-24 overflow-hidden rounded-full bg-sunken">
                <span
                  className="block h-full rounded-full bg-verified transition-[width]"
                  style={{ width: `${pct}%` }}
                />
              </span>
            </span>
          )}
        </div>
      </header>

      {!transcriptId && (
        <div className="card border-amber-200 bg-amber-50 p-4 text-sm dark:border-amber-900 dark:bg-amber-950/40">
          <p className="font-medium text-amber-900 dark:text-amber-200">
            No transcript yet.
          </p>
          <p className="mt-1 text-amber-800 dark:text-amber-300/80">
            {ep.status === 'queued' || ep.status === 'processing'
              ? 'A job is running — this page refreshes itself.'
              : 'Press Transcribe to queue this episode.'}
          </p>
          {ep.status !== 'queued' && ep.status !== 'processing' && (
            <button onClick={() => transcribe.mutate()} className="btn-primary mt-3">
              Transcribe
            </button>
          )}
        </div>
      )}

      {transcriptId && (
        <>
          {/* top-14 clears the sticky app header. */}
          <div className="sticky top-14 z-20 -mx-1 bg-canvas/90 px-1 py-1 backdrop-blur">
            <WaveformPlayer
              ref={player}
              src={api.audioUrl(transcriptId)}
              onTimeUpdate={setCurrentTime}
            />
          </div>

          <div className="card flex flex-wrap items-center gap-x-4 gap-y-3 p-3">
            <SpeakerLegend
              speakers={transcript.data?.speakers ?? []}
              utterances={utterances}
              onRename={(cluster, label) => rename.mutate({ cluster, label })}
            />
            <div className="ml-auto flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm text-muted">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(e) => setFollow(e.target.checked)}
                  className="accent-accent"
                />
                Follow
              </label>
              <ConfidenceToggle
                enabled={showConf}
                onChange={setShowConf}
                percentile={percentile}
                onPercentileChange={setPercentile}
                threshold={confThreshold}
              />
              <button
                onClick={() => setShowKeys(true)}
                className="btn-ghost btn-sm"
                title="Keyboard shortcuts (?)"
              >
                ?
              </button>
              <ExportMenu episodeId={id} />
            </div>
          </div>

          <p className="text-xs text-faint">
            Click a word to play from it. Text is stored exactly as typed — no
            spellcheck, no autocorrect. Press <b>?</b> for shortcuts.
          </p>

          {transcript.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-24 w-full rounded-xl" />
              ))}
            </div>
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
              followPlayhead={follow}
              savingId={
                saveUtterance.isPending ? (saveUtterance.variables?.utteranceId ?? null) : null
              }
            />
          )}
        </>
      )}
    </section>
  )
}
