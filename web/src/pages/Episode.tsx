// PLAN §10: "the Episode screen is the product".
//
// Layout: waveform pinned under the app header; transcript below, one card per
// utterance. No speaker labels.
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
import { ArrowLeft, Pencil, Spinner } from '../components/Icons'
import Shortcuts from '../components/Shortcuts'
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
  // Null once the audio was deleted after its Google Doc synced (app/purge_audio.py).
  const hasAudio = !!episode.data?.audio_path

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
    enabled: !!transcriptId && hasAudio,
    staleTime: Infinity,
    retry: false,
  })

  // A failed save must not silently drop what the verifier typed. saveError holds the
  // exact text that failed to save, so TranscriptEditor can reopen that block with it
  // (instead of the useEffect that resets the draft back to the server's old text on
  // close, which is what used to lose it) and show why.
  const [saveError, setSaveError] = useState<
    { utteranceId: string; text: string; message: string } | null
  >(null)
  const saveUtterance = useMutation({
    mutationFn: ({ utteranceId, text }: { utteranceId: string; text: string }) =>
      api.patchUtterance(utteranceId, { text_verified: text }),
    onSuccess: (_data, { utteranceId }) => {
      setSaveError((e) => (e?.utteranceId === utteranceId ? null : e))
      queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] })
      queryClient.invalidateQueries({ queryKey: ['episode', id] })
      // n_verified on the Episodes list card is otherwise stale for its 30s staleTime.
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
    },
    onError: (err, { utteranceId, text }) => {
      setSaveError({
        utteranceId, text,
        message: err instanceof ApiError ? err.detail : 'Không lưu được — hãy thử lại.',
      })
    },
  })

  // Fills in punctuation for utterances that have none yet or were just edited. Only
  // changed passages are recomputed server-side, so after an edit it is quick;
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
    if (!readable || !t || !t.readable_available) return
    if (!staleSig || punctuate.isPending) return
    const sig = `${t.id}:${staleSig}`
    if (lastPunctuated.current === sig) return // tried this exact state already
    lastPunctuated.current = sig
    punctuate.mutate()
  }, [readable, transcript.data, staleSig, punctuate])

  const revert = useMutation({
    mutationFn: (utteranceId: string) => api.revertUtterance(utteranceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript', transcriptId] })
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
    },
  })

  const transcribe = useMutation({
    mutationFn: () => api.transcribe(id!, { hotwords: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episode', id] }),
  })

  const utterances = useMemo(
    () => transcript.data?.utterances ?? [],
    [transcript.data],
  )
  const words = transcript.data?.words ?? []


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
  const verifiedCount = utterances.filter((u: Utterance) => u.text_verified !== null).length
  const pct = utterances.length ? (verifiedCount / utterances.length) * 100 : 0

  return (
    <section className="space-y-5">
      {showKeys && <Shortcuts onClose={() => setShowKeys(false)} />}

      <header className="pb-2">
        <Link
          to={`/projects/${ep.project_id}`}
          className="inline-flex items-center gap-2 text-sm text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" />
          Quay lại
        </Link>
        <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-2">
          <EpisodeTitle id={ep.id} title={ep.title || ep.slug} />
          <ProjectMove episodeId={ep.id} projectId={ep.project_id} />
          <StatusChip status={ep.status} />
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
            {!hasAudio ? (
              <div className="card p-3 text-sm text-muted">
                Đã xoá âm thanh của tập này để tiết kiệm dung lượng. Bản chép lời vẫn giữ
                nguyên (và có trong Google Doc), nhưng không nghe lại được.
              </div>
            ) : peaks.isPending ? (
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
              {transcript.data?.readable_available && (
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
                disabled={!transcript.data?.readable_available}
                disabledReason="Máy chủ chưa cài mô hình thêm dấu câu"
              />
            </div>
          </div>

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
              onWordClick={(w) => seekTo(w.start_s)}
              onSave={(utteranceId, text) => saveUtterance.mutate({ utteranceId, text })}
              onRevert={(utteranceId) => revert.mutate(utteranceId)}
              saveError={saveError}
              confThreshold={confThreshold}
              activeIndex={activeIndex}
              onActivate={setActiveIndex}
              followPlayhead={follow}
              readable={readable}
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

/** A small "move to another project" select, next to the title. */
function ProjectMove({ episodeId, projectId }: { episodeId: string; projectId: string }) {
  const queryClient = useQueryClient()
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api.listProjects() })
  const move = useMutation({
    mutationFn: (next: string) => api.moveEpisode(episodeId, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['episode', episodeId] })
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const rows = projects.data ?? []
  if (rows.length < 2) return null // nothing to move to
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      Dự án
      <select
        value={projectId}
        disabled={move.isPending}
        onChange={(e) => e.target.value !== projectId && move.mutate(e.target.value)}
        className="field w-auto py-1 text-xs"
      >
        {rows.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </label>
  )
}

/** The page title, with a pencil to rename the episode in place (Enter saves, Esc cancels). */
function EpisodeTitle({ id, title }: { id: string; title: string }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)
  const rename = useMutation({
    mutationFn: (next: string) => api.renameEpisode(id, next),
    onSuccess: () => {
      setDraft(null)
      queryClient.invalidateQueries({ queryKey: ['episode', id] })
      queryClient.invalidateQueries({ queryKey: ['episodes'] })
    },
  })

  if (draft === null) {
    return (
      <span className="flex min-w-0 items-center gap-1.5">
        <h1 className="title min-w-0 break-words">{title}</h1>
        <button
          onClick={() => setDraft(title)}
          className="btn-ghost btn-sm shrink-0"
          title="Đổi tên tập"
          aria-label="Đổi tên tập"
        >
          <Pencil />
        </button>
      </span>
    )
  }

  const save = () => {
    const next = draft.trim()
    if (!next || next === title) setDraft(null)
    else rename.mutate(next)
  }
  return (
    <form
      className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto sm:flex-1"
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
    >
      <input
        autoFocus
        value={draft}
        maxLength={300}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setDraft(null)
        }}
        className="field min-w-0 flex-1 text-base"
        aria-label="Tên tập"
      />
      <button type="submit" className="btn-primary btn-sm" disabled={rename.isPending}>
        {rename.isPending ? <Spinner className="h-3.5 w-3.5" /> : 'Lưu'}
      </button>
      <button type="button" className="btn-ghost btn-sm" onClick={() => setDraft(null)}>
        Huỷ
      </button>
      {rename.isError && (
        <span className="w-full text-xs text-rose-600">
          {rename.error instanceof ApiError ? rename.error.detail : 'Không đổi được tên'}
        </span>
      )}
    </form>
  )
}
