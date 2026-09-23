// "Show confidence" — highlight words below a percentile of conf (PLAN §10).
//
// conf is a mean log-prob: lower is worse, and it is null when the runtime gave no
// ys_log_probs. A null must render as "no signal", never as "low confidence" — an
// absent measurement is not a bad one.

import type { Word } from '../api/types'

/** The conf value at `percentile` (0–100) over the words that have one. */
export function confPercentile(words: Word[], percentile = 15): number | null {
  const values = words
    .map((w) => w.conf)
    .filter((c): c is number => c !== null)
    .sort((a, b) => a - b)
  if (values.length === 0) return null
  const index = Math.min(
    values.length - 1,
    Math.max(0, Math.floor((percentile / 100) * values.length)),
  )
  return values[index]
}

export interface ConfidenceToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  percentile?: number
  onPercentileChange?: (percentile: number) => void
  threshold: number | null
}

export default function ConfidenceToggle({
  enabled,
  onChange,
  percentile = 15,
  onPercentileChange,
  threshold,
}: ConfidenceToggleProps) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      Hiện độ tin cậy
      {enabled && (
        <>
          <input
            type="range"
            min={5}
            max={50}
            step={5}
            value={percentile}
            onChange={(e) => onPercentileChange?.(Number(e.target.value))}
          />
          <span className="text-xs text-muted">
            dưới p{percentile}
            {threshold !== null ? ` (${threshold.toFixed(2)})` : ' (không có dữ liệu)'}
          </span>
        </>
      )}
    </label>
  )
}
