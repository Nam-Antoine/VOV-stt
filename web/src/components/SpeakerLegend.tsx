// Per-episode cluster → free-text label (PLAN §10, §0.3).
//
// This is NOT speaker identification. A label applies to one episode's cluster and
// carries no identity across episodes; the vox-pop voices are identifiable private
// individuals and building recognition for them is out of scope by policy.

import { useState } from 'react'

import type { Speaker } from '../api/types'

/** Stable colour per cluster so the same speaker keeps its colour down the page. */
export const SPEAKER_COLOURS = [
  '#2563eb', '#db2777', '#16a34a', '#d97706', '#7c3aed',
  '#0891b2', '#dc2626', '#4d7c0f', '#9333ea', '#0f766e',
] as const

export function speakerColour(cluster: number): string {
  if (cluster < 0) return '#94a3b8'
  return SPEAKER_COLOURS[cluster % SPEAKER_COLOURS.length]
}

export interface SpeakerLegendProps {
  speakers: Speaker[]
  onRename: (cluster: number, label: string) => void
}

export default function SpeakerLegend({ speakers, onRename }: SpeakerLegendProps) {
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  return (
    <div className="flex flex-wrap items-center gap-2">
      {speakers.map((s) =>
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
            className="w-40 rounded border border-slate-300 px-2 py-0.5 text-xs"
            placeholder="e.g. MC Thanh Huyền"
          />
        ) : (
          <button
            key={s.cluster}
            onClick={() => {
              setDraft(s.label ?? '')
              setEditing(s.cluster)
            }}
            title="Click to rename for this episode"
            className="rounded-full px-2.5 py-1 text-xs text-white"
            style={{ backgroundColor: speakerColour(s.cluster) }}
          >
            {s.label ?? `SPEAKER_${String(s.cluster).padStart(2, '0')}`}
          </button>
        ),
      )}
      {speakers.length === 0 && (
        <span className="text-xs text-slate-400">No speaker clusters yet.</span>
      )}
    </div>
  )
}
