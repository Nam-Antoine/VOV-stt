// Utterances grouped by speaker, with inline-editable text (PLAN §10).
//
// The three attributes below are not cosmetic. The browser will happily capitalise the
// first letter of an utterance, "fix" a repeated word, or autocorrect a dialect form —
// and that silently destroys the corpus (PLAN §0.1, CLAUDE.md rule 1). They must stay
// on every editable element.
export const NO_AUTOCORRECT = {
  spellCheck: false,
  autoCapitalize: 'off',
  autoCorrect: 'off',
} as const

import { useEffect, useRef, useState } from 'react'

import type { Utterance, Word } from '../api/types'
import { displayText } from '../api/types'
import { speakerColour, speakerName } from './SpeakerLegend'

export interface TranscriptEditorProps {
  utterances: Utterance[]
  words: Word[]
  speakerLabels: Record<number, string>
  /** Click a word → seek and play from it. */
  onWordClick: (word: Word) => void
  onSave: (utteranceId: string, text: string) => void
  onRevert?: (utteranceId: string) => void
  /** Words below this conf get a dotted underline (PLAN §10, 15th percentile). */
  confThreshold?: number | null
  activeIndex?: number
  onActivate?: (index: number) => void
  /** Scroll the playing utterance into view. Off while the reader is driving. */
  followPlayhead?: boolean
  /** id of the utterance currently being written to the API. */
  savingId?: string | null
  /** Text-first preview: speakers are still being worked out, so nothing is editable. */
  readOnly?: boolean
  /** Show the punctuated reading layer where it is up to date. Editing is always on
   *  the verbatim text. */
  readable?: boolean
}

function timestamp(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function UtteranceBlock({
  utterance,
  words,
  speakerLabels,
  onWordClick,
  onSave,
  onRevert,
  confThreshold,
  active,
  follow,
  saving,
  continued,
  readOnly,
  readable,
  onActivate,
}: {
  utterance: Utterance
  words: Word[]
  speakerLabels: Record<number, string>
  onWordClick: (w: Word) => void
  onSave: (id: string, text: string) => void
  onRevert?: (id: string) => void
  confThreshold: number | null
  active: boolean
  follow: boolean
  saving: boolean
  /** Same speaker as the utterance above: the margin shows only the time. */
  continued: boolean
  readOnly: boolean
  readable: boolean
  onActivate?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => displayText(utterance))
  const box = useRef<HTMLTextAreaElement>(null)
  const article = useRef<HTMLElement>(null)
  const saved = displayText(utterance)
  const dirty = editing && draft !== saved
  const colour = speakerColour(utterance.speaker)

  useEffect(() => {
    if (!editing) setDraft(saved)
  }, [saved, editing])

  useEffect(() => {
    if (editing) box.current?.focus()
  }, [editing])

  // Follow the playhead down the page, but never yank the view while someone is
  // typing into this block.
  useEffect(() => {
    if (active && follow && !editing) {
      article.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [active, follow, editing])

  const verified = utterance.text_verified !== null
  const reading = readable ? utterance.text_readable : null
  // The reading layer only adds marks and case, so it has exactly one token per word;
  // when it does, each punctuated token stays a click-to-play word.
  const readingTokens = reading?.split(/\s+/).filter(Boolean) ?? null
  const shown =
    readingTokens && readingTokens.length === words.length
      ? words.map((w, k) => ({ ...w, text: readingTokens[k] }))
      : words

  return (
    <article
      ref={article}
      onClick={onActivate}
      onDoubleClick={() => !readOnly && setEditing(true)}
      className={`utterance-anchor group relative grid gap-x-8 gap-y-1 px-4 py-4 sm:grid-cols-[9rem_1fr] sm:px-5 ${
        continued ? '' : 'border-t border-line first:border-t-0'
      } ${active ? 'bg-sunken' : 'hover:bg-sunken/60'} ${
        dirty ? 'bg-dirty/10' : ''
      }`}
    >
      {/* The speaker's colour is a thin rule, not a painted box. */}
      <span
        aria-hidden="true"
        className={`absolute inset-y-0 left-0 w-[3px] transition-opacity ${
          active || dirty ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'
        }`}
        style={{ backgroundColor: dirty ? undefined : colour }}
      />

      <header className="flex items-baseline gap-2 text-xs sm:flex-col sm:gap-0.5 sm:pt-1">
        {!continued && !readOnly && (
          <span className="flex items-center gap-1.5 font-semibold tracking-wide">
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: colour }}
            />
            <span className="truncate">{speakerName(speakerLabels, utterance.speaker)}</span>
          </span>
        )}
        <span className={`tabular-nums text-faint ${continued || readOnly ? '' : 'sm:pl-3.5'}`}>
          {timestamp(utterance.start_s)}
        </span>
        {saving ? (
          <span className="text-faint sm:pl-3.5">đang lưu…</span>
        ) : verified ? (
          <span
            className="flex items-center gap-1 font-medium text-verified dark:text-[#9cc487] sm:pl-3.5"
            title={
              utterance.verified_by
                ? `sửa bởi ${utterance.verified_by}`
                : 'đã được người sửa'
            }
          >
            <span aria-hidden="true">✓</span> đã duyệt
          </span>
        ) : null}
      </header>

      <div className="min-w-0">
        {editing ? (
          <>
            <textarea
              ref={box}
              {...NO_AUTOCORRECT}
              value={draft}
              rows={Math.max(2, Math.ceil(draft.length / 80))}
              onChange={(e) => setDraft(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onBlur={() => {
                // Save exactly what is in the box. No trim(), no whitespace collapsing.
                if (draft !== saved) onSave(utterance.id, draft)
                setEditing(false)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  setDraft(saved)
                  setEditing(false)
                }
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.currentTarget.blur()
                }
              }}
              className="w-full max-w-measure resize-y rounded-md border border-accent-strong/60 bg-canvas p-3 font-transcript text-utterance text-ink shadow-inner focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-accent-strong/20"
            />
            {readable && (
              <p className="mt-1.5 text-xs text-faint">
                Đang sửa văn bản nguyên văn — dấu câu sẽ được thêm lại tự động sau khi lưu.
              </p>
            )}
            <p className="mt-1.5 text-xs text-faint">
              Esc để hủy · ⌘/Ctrl + Enter để lưu · lưu nguyên văn, không tự sửa
            </p>
          </>
        ) : (
          <p className="max-w-measure whitespace-pre-wrap font-transcript text-utterance">
            {reading && shown === words && words.length > 0
              ? reading
              : shown.length > 0
              ? shown.map((w) => {
                  const low =
                    confThreshold !== null && w.conf !== null && w.conf < confThreshold
                  return (
                    <span
                      key={w.i}
                      onClick={(e) => {
                        e.stopPropagation()
                        onWordClick(w)
                      }}
                      title={`${timestamp(w.start_s)} — nhấp để phát từ đây`}
                      className={`cursor-pointer rounded-sm transition-colors hover:bg-accent/15 hover:text-accent-strong ${
                        low ? 'word-low-conf' : ''
                      }`}
                    >
                      {w.text}{' '}
                    </span>
                  )
                })
              : (reading ?? saved)}
          </p>
        )}
      </div>

      {/* Actions sit in the top-right corner and only surface on hover / focus /
          the active line, so a page of 31 turns is not 31 rows of buttons. */}
      <div
        className={`absolute right-3 top-3 flex items-center gap-1 transition-opacity ${
          active || editing ? 'opacity-100' : 'opacity-0 focus-within:opacity-100 group-hover:opacity-100'
        }`}
      >
        {!editing && !readOnly && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setEditing(true)
            }}
            className="btn-outline btn-sm"
          >
            Sửa
          </button>
        )}
        {verified && onRevert && !readOnly && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRevert(utterance.id)
              setEditing(false)
            }}
            className="btn-ghost btn-sm hover:text-[#b5402a]"
            title="Khôi phục văn bản gốc của máy"
          >
            Khôi phục
          </button>
        )}
      </div>
    </article>
  )
}

export default function TranscriptEditor({
  utterances,
  words,
  speakerLabels,
  onWordClick,
  onSave,
  onRevert,
  confThreshold = null,
  activeIndex = -1,
  onActivate,
  followPlayhead = false,
  savingId = null,
  readOnly = false,
  readable = false,
}: TranscriptEditorProps) {
  // Bucket words by utterance once, by time span: the API sends both lists flat and a
  // per-utterance filter would be O(utterances x words) on a few thousand words.
  const buckets = new Map<number, Word[]>()
  let cursor = 0
  for (const u of utterances) {
    const bucket: Word[] = []
    while (cursor < words.length && words[cursor].start_s < u.start_s) cursor++
    while (cursor < words.length && words[cursor].start_s < u.end_s) {
      bucket.push(words[cursor])
      cursor++
    }
    buckets.set(u.i, bucket)
  }

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-canvas">
      {utterances.map((u, index) => (
        <UtteranceBlock
          key={u.id}
          utterance={u}
          words={u.text_verified === null ? (buckets.get(u.i) ?? []) : []}
          speakerLabels={speakerLabels}
          onWordClick={onWordClick}
          onSave={onSave}
          onRevert={onRevert}
          confThreshold={confThreshold}
          active={index === activeIndex}
          follow={followPlayhead}
          saving={savingId === u.id}
          continued={index > 0 && utterances[index - 1].speaker === u.speaker}
          readOnly={readOnly}
          readable={readable}
          onActivate={() => onActivate?.(index)}
        />
      ))}
      {utterances.length === 0 && (
        <p className="py-12 text-center text-muted">Bản chép lời này không có lượt lời nào.</p>
      )}
    </div>
  )
}
