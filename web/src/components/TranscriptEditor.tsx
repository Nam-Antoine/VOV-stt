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
import { speakerColour } from './SpeakerLegend'

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
}

function timestamp(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function label(speakerLabels: Record<number, string>, speaker: number) {
  if (speakerLabels[speaker]) return speakerLabels[speaker]
  if (speaker < 0) return 'SPEAKER_UNKNOWN'
  return `SPEAKER_${String(speaker).padStart(2, '0')}`
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
  onActivate?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => displayText(utterance))
  const box = useRef<HTMLTextAreaElement>(null)
  const saved = displayText(utterance)
  const dirty = editing && draft !== saved

  useEffect(() => {
    if (!editing) setDraft(saved)
  }, [saved, editing])

  useEffect(() => {
    if (editing) box.current?.focus()
  }, [editing])

  return (
    <article
      onClick={onActivate}
      className={`rounded border bg-white p-3 ${
        active ? 'border-slate-900' : 'border-slate-200'
      } ${dirty ? 'ring-2 ring-amber-400' : ''}`}
    >
      <header className="mb-1 flex items-center gap-2 text-xs">
        <span
          className="rounded-full px-2 py-0.5 text-white"
          style={{ backgroundColor: speakerColour(utterance.speaker) }}
        >
          {label(speakerLabels, utterance.speaker)}
        </span>
        <span className="tabular-nums text-slate-400">
          {timestamp(utterance.start_s)}
        </span>
        {utterance.text_verified !== null && (
          <span className="text-emerald-600">verified</span>
        )}
        <span className="ml-auto flex gap-2">
          {!editing && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setEditing(true)
              }}
              className="text-slate-400 hover:text-slate-900"
            >
              edit
            </button>
          )}
          {utterance.text_verified !== null && onRevert && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onRevert(utterance.id)
                setEditing(false)
              }}
              className="text-slate-400 hover:text-rose-600"
              title="Revert to the engine's text"
            >
              revert
            </button>
          )}
        </span>
      </header>

      {editing ? (
        <textarea
          ref={box}
          {...NO_AUTOCORRECT}
          value={draft}
          rows={Math.max(2, Math.ceil(draft.length / 90))}
          onChange={(e) => setDraft(e.target.value)}
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
          }}
          className="w-full resize-y rounded border border-slate-300 p-2 font-transcript"
        />
      ) : (
        <p className="whitespace-pre-wrap leading-relaxed">
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
                    className={`cursor-pointer hover:bg-amber-100 ${
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
          onActivate={() => onActivate?.(index)}
        />
      ))}
      {utterances.length === 0 && (
        <p className="text-slate-400">No utterances in this transcript.</p>
      )}
    </div>
  )
}
