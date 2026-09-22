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

  return (
    <article
      ref={article}
      onClick={onActivate}
      onDoubleClick={() => setEditing(true)}
      className={`utterance-anchor rounded-xl border-l-[3px] bg-surface py-3 pl-3 pr-3 transition-shadow ${
        active ? 'shadow-sm ring-1 ring-accent/40' : 'ring-1 ring-line'
      } ${dirty ? 'ring-2 ring-dirty' : ''}`}
      style={{ borderLeftColor: colour }}
    >
      <header className="mb-1.5 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold" style={{ color: colour }}>
          {speakerName(speakerLabels, utterance.speaker)}
        </span>
        <span className="tabular-nums text-faint">{timestamp(utterance.start_s)}</span>

        {saving ? (
          <span className="text-faint">saving…</span>
        ) : utterance.text_verified !== null ? (
          <span
            className="chip bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            title={
              utterance.verified_by
                ? `edited by ${utterance.verified_by}`
                : 'human-edited'
            }
          >
            verified
          </span>
        ) : null}

        <span className="ml-auto flex items-center gap-1">
          {!editing && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setEditing(true)
              }}
              className="btn-ghost btn-sm"
            >
              Edit
            </button>
          )}
          {utterance.text_verified !== null && onRevert && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onRevert(utterance.id)
                setEditing(false)
              }}
              className="btn-ghost btn-sm hover:text-rose-600"
              title="Revert to the engine's text"
            >
              Revert
            </button>
          )}
        </span>
      </header>

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
            className="w-full resize-y rounded-lg border border-line bg-canvas p-2.5 font-transcript text-utterance text-ink focus:border-accent focus:outline-none"
          />
          <p className="mt-1 text-xs text-faint">
            Esc discards · ⌘/Ctrl + Enter saves · stored byte for byte, no autocorrect
          </p>
        </>
      ) : (
        <p className="max-w-measure whitespace-pre-wrap text-utterance">
          {words.length > 0
            ? words.map((w) => {
                const low =
                  confThreshold !== null && w.conf !== null && w.conf < confThreshold
                return (
                  <span
                    key={w.i}
                    onClick={(e) => {
                      e.stopPropagation()
                      onWordClick(w)
                    }}
                    title={`${timestamp(w.start_s)} — click to play from here`}
                    className={`cursor-pointer rounded-sm hover:bg-accent/15 ${
                      low ? 'word-low-conf' : ''
                    }`}
                  >
                    {w.text}{' '}
                  </span>
                )
              })
            : saved}
        </p>
      )}
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
    <div className="space-y-2">
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
          onActivate={() => onActivate?.(index)}
        />
      ))}
      {utterances.length === 0 && (
        <p className="py-8 text-center text-muted">No utterances in this transcript.</p>
      )}
    </div>
  )
}
