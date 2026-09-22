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

import type { Utterance, Word } from '../api/types'
import { displayText } from '../api/types'

export interface TranscriptEditorProps {
  utterances: Utterance[]
  words: Word[]
  speakerLabels: Record<number, string>
  /** Click a word → seek and play from it. */
  onWordClick: (word: Word) => void
  onSave: (utteranceId: string, text: string) => void
  /** Words below this conf get a dotted underline (PLAN §10, 15th percentile). */
  confThreshold?: number | null
  currentTime?: number
}

export default function TranscriptEditor({
  utterances,
  words,
  speakerLabels,
  onWordClick,
  onSave,
  confThreshold = null,
}: TranscriptEditorProps) {
  // TODO(T4):
  //   - render one block per utterance: speaker chip (coloured, click to relabel),
  //     timestamp, then the words
  //   - a word is a <span> with onClick={() => onWordClick(w)}
  //   - the utterance body is contentEditable with {...NO_AUTOCORRECT}
  //   - dirty state → amber ring; save on blur via onSave (optimistic PATCH)
  //   - Ctrl+Z on a dirty utterance reverts to text_asr
  //   - highlight the utterance containing currentTime
  //   - never transform the string between the DOM and onSave: no trim(), no
  //     replace(/\s+/g, ' '), no smart quotes
  return (
    <div className="space-y-3">
      <p className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        TranscriptEditor — T4. {utterances.length} utterances, {words.length} words.
        Speaker labels: {Object.keys(speakerLabels).length}.
        {confThreshold !== null && ` Confidence cutoff: ${confThreshold}.`}
      </p>
      {utterances.slice(0, 3).map((u) => (
        <article key={u.id} className="rounded border border-slate-200 bg-white p-3">
          <header className="mb-1 text-xs text-slate-500">
            {speakerLabels[u.speaker] ?? `SPEAKER_${String(u.speaker).padStart(2, '0')}`}
            {' · '}
            {u.start_s.toFixed(2)}s
          </header>
          <div {...NO_AUTOCORRECT} className="whitespace-pre-wrap">
            {displayText(u)}
          </div>
        </article>
      ))}
    </div>
  )
}
