// Per-episode cluster → free-text label (PLAN §10, §0.3).
//
// This is NOT speaker identification. A label applies to one episode's cluster and
// carries no identity across episodes; the vox-pop voices are identifiable private
// individuals and building recognition for them is out of scope by policy.

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
  // TODO(T4): inline-edit each label; PUT /episodes/{id}/speakers/{cluster} on blur,
  // optimistic so the chips down the transcript update immediately.
  return (
    <div className="flex flex-wrap gap-2">
      {speakers.map((s) => (
        <span
          key={s.cluster}
          className="rounded-full px-2.5 py-1 text-xs text-white"
          style={{ backgroundColor: speakerColour(s.cluster) }}
        >
          {s.label ?? `SPEAKER_${String(s.cluster).padStart(2, '0')}`}
        </span>
      ))}
      {speakers.length === 0 && (
        <span className="text-xs text-slate-400">No speaker clusters yet.</span>
      )}
    </div>
  )
}
