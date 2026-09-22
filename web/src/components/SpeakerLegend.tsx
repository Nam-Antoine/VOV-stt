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
  '#2563eb', '#db2777', '#16a34a', '#d97706', '#7c3aed',
  '#0891b2', '#dc2626', '#4d7c0f', '#9333ea', '#0f766e',
] as const

export function speakerColour(cluster: number): string {
  if (cluster < 0) return '#94a3b8'
  return SPEAKER_COLOURS[cluster % SPEAKER_COLOURS.length]
}

export function speakerName(labels: Record<number, string>, cluster: number): string {
  if (labels[cluster]) return labels[cluster]
  if (cluster < 0) return 'SPEAKER_UNKNOWN'
  return `SPEAKER_${String(cluster).padStart(2, '0')}`
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
            className="w-44 rounded-full border border-line bg-surface px-3 py-1 text-xs focus:border-accent focus:outline-none"
            placeholder="e.g. MC Thanh Huyền"
          />
        ) : (
          <button
            key={s.cluster}
            onClick={() => {
              setDraft(s.label ?? '')
              setEditing(s.cluster)
            }}
            title={`${Math.round(s.seconds)}s of speech — click to rename for this episode`}
            className="group inline-flex items-center gap-1.5 rounded-full py-1 pl-1.5 pr-2.5 text-xs font-medium text-white transition-opacity hover:opacity-85"
            style={{ backgroundColor: speakerColour(s.cluster) }}
          >
            <span
              className="h-2 w-2 rounded-full bg-white/70"
              aria-hidden="true"
            />
            {s.label ?? `SPEAKER_${String(s.cluster).padStart(2, '0')}`}
            {total > 0 && (
              <span className="tabular-nums opacity-70">
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
          {expanded ? 'Show fewer' : `${hidden} more`}
          <Chevron className={`h-3 w-3 ${expanded ? 'rotate-180' : ''}`} />
        </button>
      )}

      {speakers.length === 0 && (
        <span className="text-xs text-faint">No speaker clusters yet.</span>
      )}
    </div>
  )
}
