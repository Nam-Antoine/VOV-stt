// Per-episode cluster → free-text label (PLAN §10, §0.3).
//
// This is NOT speaker identification. A label applies to one episode's cluster and
// carries no identity across episodes; the vox-pop voices are identifiable private
// individuals and building recognition for them is out of scope by policy.
//
// Clustering on a 14-minute episode produces ~11 clusters for what is really two
// hosts plus callers, so the legend is ordered by talk time and the long tail is
// folded away. The people worth naming are the ones who talk, and they are first.

import { useMemo, useState } from 'react'

import type { Speaker, Utterance } from '../api/types'
import { Chevron } from './Icons'

/** Stable colour per cluster so the same speaker keeps its colour down the page. */
export const SPEAKER_COLOURS = [
  // Earthy mid-tones: ~4:1 against both the paper and the charcoal ground, so the
  // same hue works as a label in light and dark mode.
  '#3a7ca5', '#b5533c', '#5b8c3e', '#b8860b', '#8360a8',
  '#2f8c80', '#b04a76', '#7c7c32', '#5271c4', '#9a6a45',
] as const

export function speakerColour(cluster: number): string {
  if (cluster < 0) return '#8f8577'
  return SPEAKER_COLOURS[cluster % SPEAKER_COLOURS.length]
}

export function speakerName(labels: Record<number, string>, cluster: number): string {
  if (labels[cluster]) return labels[cluster]
  if (cluster < 0) return 'Người nói không rõ'
  return `Người nói ${String(cluster).padStart(2, '0')}`
}

/** Seconds of speech per cluster, for ordering and for the share percentages. */
export function talkTimes(utterances: Utterance[]): Map<number, number> {
  const totals = new Map<number, number>()
  for (const u of utterances) {
    totals.set(u.speaker, (totals.get(u.speaker) ?? 0) + (u.end_s - u.start_s))
  }
  return totals
}

/** Clusters below this share of speech go behind "show all". */
const TAIL_SHARE = 0.03
const ALWAYS_SHOWN = 4

export interface SpeakerLegendProps {
  speakers: Speaker[]
  utterances?: Utterance[]
  onRename: (cluster: number, label: string) => void
}

export default function SpeakerLegend({
  speakers,
  utterances = [],
  onRename,
}: SpeakerLegendProps) {
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [expanded, setExpanded] = useState(false)

  const { ordered, total } = useMemo(() => {
    const totals = talkTimes(utterances)
    const sum = [...totals.values()].reduce((a, b) => a + b, 0)
    const ordered = [...speakers].sort(
      (a, b) => (totals.get(b.cluster) ?? 0) - (totals.get(a.cluster) ?? 0),
    )
    return {
      ordered: ordered.map((s) => ({ ...s, seconds: totals.get(s.cluster) ?? 0 })),
      total: sum,
    }
  }, [speakers, utterances])

  const major = ordered.filter(
    (s, i) => i < ALWAYS_SHOWN || (total > 0 && s.seconds / total >= TAIL_SHARE),
  )
  const hidden = ordered.length - major.length
  const shown = expanded ? ordered : major

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {shown.map((s) =>
        editing === s.cluster ? (
          <input
            key={s.cluster}
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => {
              if (draft !== (s.label ?? '')) onRename(s.cluster, draft)
              setEditing(null)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') setEditing(null)
            }}
            className="w-44 rounded-full border border-line bg-surface px-3 py-1 text-xs focus:border-accent-strong focus:outline-none"
            placeholder="vd. MC Thanh Huyền"
          />
        ) : (
          <button
            key={s.cluster}
            onClick={() => {
              setDraft(s.label ?? '')
              setEditing(s.cluster)
            }}
            title={`${Math.round(s.seconds)} giây nói — nhấp để đặt tên cho tập này`}
            className="group inline-flex items-center gap-1.5 rounded-full border border-line bg-canvas py-1 pl-2 pr-2.5 text-xs font-medium text-ink transition-colors hover:border-faint"
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: speakerColour(s.cluster) }}
              aria-hidden="true"
            />
            {s.label ?? `Người nói ${String(s.cluster).padStart(2, '0')}`}
            {total > 0 && (
              <span className="tabular-nums text-faint">
                {Math.round((s.seconds / total) * 100)}%
              </span>
            )}
          </button>
        ),
      )}

      {hidden > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="btn-ghost btn-sm rounded-full"
        >
          {expanded ? 'Thu gọn' : `thêm ${hidden}`}
          <Chevron className={`h-3 w-3 ${expanded ? 'rotate-180' : ''}`} />
        </button>
      )}

      {speakers.length === 0 && (
        <span className="text-xs text-faint">Chưa có nhóm người nói nào.</span>
      )}
    </div>
  )
}
