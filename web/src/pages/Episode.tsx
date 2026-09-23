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
import ExportMenu, { SPEAKERS_PENDING } from '../components/ExportMenu'
import { ArrowLeft, Spinner } from '../components/Icons'
import Shortcuts from '../components/Shortcuts'
import SpeakerLegend from '../components/SpeakerLegend'
import TranscriptEditor from '../components/TranscriptEditor'
import WaveformPlayer, { type WaveformPlayerHandle } from '../components/WaveformPlayer'
import { StatusChip } from './Episodes'
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
  // The client reads punctuated text; default on, remembered per browser.
  const [readable, setReadable] = useState(() => {
    try {
      return localStorage.getItem('vnstt.readable') !== '0'
    } catch {
      return true
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem('vnstt.readable', readable ? '1' : '0')
    } catch {
      /* private mode: not remembered, still works */
    }
  }, [readable])

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

  // Fetched before the player mounts so wavesurfer is created once, with peaks, and
  // never starts a full download-and-decode it would then throw away.
  const peaks = useQuery({
    queryKey: ['peaks', transcriptId],
    queryFn: () => api.getPeaks(transcriptId!),
    enabled: !!transcriptId,
    staleTime: Infinity,
    retry: false,
  })

  const saveUtterance = useMutation({
    mutationFn: ({ utteranceId, text }: { utteranceId: string; text: string }) =>
      api.patchUtterance(utteranceId, { text_verified: text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] })
      queryClient.invalidateQueries({ queryKey: ['episode', id] })
    },
  })

  // Fills in punctuation for utterances that have none yet or were just edited. Only
  // changed speaker turns are recomputed server-side, so after an edit it is quick;
  // an episode transcribed before this existed takes ~20 s once.
  const punctuate = useMutation({
    mutationFn: () => api.refreshReadable(transcriptId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] }),
  })
  const staleSig = (transcript.data?.utterances ?? [])
    .filter((u) => u.text_readable === null)
    .map((u) => u.id)
    .join(',')
  const lastPunctuated = useRef('')
  useEffect(() => {
    const t = transcript.data
    if (!readable || !t || !t.readable_available || t.speakers_pending) return
    if (!staleSig || punctuate.isPending) return
    const sig = `${t.id}:${staleSig}`
    if (lastPunctuated.current === sig) return // tried this exact state already
    lastPunctuated.current = sig
    punctuate.mutate()
  }, [readable, transcript.data, staleSig, punctuate])

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
        <Spinner className="h-4 w-4" /> Đang tải…
      </div>
    )
  }
  if (episode.isError) {
    return (
      <p className="text-rose-600">
        {episode.error instanceof ApiError ? episode.error.detail : 'Không tải được dữ liệu'}
      </p>
    )
  }

  const ep = episode.data!
  // Text-first preview: ASR text is in, diarization is still running (edits would 409).
  const pending = ep.speakers_pending || transcript.data?.speakers_pending === true
  const verifiedCount = utterances.filter((u: Utterance) => u.text_verified !== null).length
  const pct = utterances.length ? (verifiedCount / utterances.length) * 100 : 0

  return (
    <section className="space-y-5">
      {showKeys && <Shortcuts onClose={() => setShowKeys(false)} />}

      <header className="pb-2">
        <Link
          to="/episodes"
          className="inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Quay lại
        </Link>
        <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-2">
          <h1 className="title min-w-0 break-words">{ep.title || ep.slug}</h1>
          <StatusChip status={ep.status} speakersPending={pending} />
          {utterances.length > 0 && (
            <span className="flex w-full items-center gap-3 text-sm text-muted sm:ml-auto sm:w-auto">
              <span className="tabular-nums">
                <span className="font-reading text-lg text-ink">{verifiedCount}</span>
                <span className="text-faint"> / {utterances.length} đã duyệt</span>
              </span>
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-sunken sm:w-32 sm:flex-none">
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
        <div className="card p-6 text-sm">
          <p className="font-reading text-lg text-ink">Chưa có bản chép lời.</p>
          <p className="mt-1 text-muted">
            {ep.status === 'queued' || ep.status === 'processing'
              ? 'Đang xử lý — trang sẽ tự làm mới.'
              : 'Bấm Chép lời để đưa tập này vào hàng chờ.'}
          </p>
          {ep.status !== 'queued' && ep.status !== 'processing' && (
            <button onClick={() => transcribe.mutate()} className="btn-primary mt-3">
              Chép lời
            </button>
          )}
        </div>
      )}

      {transcriptId && (
        <>
          {/* Clears the sticky two-row header below lg; on desktop the nav is a sidebar. */}
          <div className="sticky top-[5.875rem] z-20 -mx-1 bg-canvas/90 px-1 py-1 backdrop-blur lg:top-0">
            {peaks.isPending ? (
              <div className="card p-3">
                <div className="skeleton h-[72px] w-full" />
                <div className="mt-2 h-9" />
              </div>
            ) : (
              <WaveformPlayer
                ref={player}
                src={api.audioUrl(transcriptId)}
                peaks={peaks.data ?? null}
                onTimeUpdate={setCurrentTime}
              />
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-line pb-4">
            {pending ? (
              <p className="flex items-center gap-2 text-sm text-muted">
                <span
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-strong"
                  aria-hidden="true"
                />
                Đang xác định người nói…
              </p>
            ) : (
              <SpeakerLegend
                speakers={transcript.data?.speakers ?? []}
                utterances={utterances}
                onRename={(cluster, label) => rename.mutate({ cluster, label })}
              />
            )}
            <div className="ml-auto flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm text-muted">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(e) => setFollow(e.target.checked)}
                  className="accent-accent"
                />
                Tự cuộn
              </label>
              {transcript.data?.readable_available && !pending && (
                <label
                  className="flex items-center gap-1.5 text-sm text-muted"
                  title="Thêm dấu câu và viết hoa để dễ đọc. Chỉ là bản đọc — văn bản nguyên văn không đổi."
                >
                  <input
                    type="checkbox"
                    checked={readable}
                    onChange={(e) => setReadable(e.target.checked)}
                    className="accent-accent"
                  />
                  Hiện dấu câu
                  {readable && punctuate.isPending && (
                    <span className="text-xs text-faint">(đang thêm…)</span>
                  )}
                </label>
              )}
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
                title="Phím tắt (?)"
              >
                ?
              </button>
              <ExportMenu
                episodeId={id}
                disabled={pending || !transcript.data?.readable_available}
                disabledReason={pending ? SPEAKERS_PENDING : 'Máy chủ chưa cài mô hình thêm dấu câu'}
              />
            </div>
          </div>

          {pending && (
            <div className="rounded-xl border border-line bg-accent/20 px-4 py-3 text-sm">
              <p className="font-medium text-ink">Đã có văn bản — đang xác định người nói.</p>
              <p className="mt-0.5 text-muted">
                Bạn có thể nghe và đọc ngay. Việc sửa sẽ mở khi phân tách người nói xong; trang
                tự làm mới.
              </p>
            </div>
          )}

          <p className="text-xs leading-relaxed text-faint">
            Nhấp vào một từ để phát từ vị trí đó. Văn bản được lưu đúng như khi gõ — không
            kiểm tra chính tả, không tự sửa. Bấm <b>?</b> để xem phím tắt.
          </p>

          {transcript.isLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-20 w-full rounded-lg" />
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
              readOnly={pending}
              readable={readable && !pending}
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
