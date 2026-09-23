// wavesurfer.js player (PLAN §6, §10). Pinned below the app header on the Episode
// screen, so it stays reachable through a 3000-word transcript.
//
// The one interaction that matters: seek to a word's start and play from there, within
// ~200 ms of the true onset (PLAN §2.2). Word `end` is the next word's start, so the
// player seeks on `start` and never tries to be cleverer about the boundary.

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'

import { Loop, Pause, Play } from './Icons'

export interface WaveformPlayerHandle {
  /** Seek to a time in seconds and start playing. Used by word clicks. */
  seekAndPlay(seconds: number): void
  playPause(): void
  /** Loop a span until told otherwise (the `L` shortcut). */
  loop(start: number, end: number): void
  clearLoop(): void
  currentTime(): number
}

export interface WaveformPlayerProps {
  /** api.audioUrl(transcriptId) — range-request streaming (compressed copy or WAV). */
  src: string
  /**
   * Server-computed waveform. With it the player draws at once and streams the audio
   * through <audio>; without it wavesurfer has to download and decode the whole file
   * first (~10-15 s for a 14-minute episode).
   */
  peaks?: { duration: number; peaks: number[] } | null
  onTimeUpdate?: (seconds: number) => void
  onReady?: (duration: number) => void
}

function clock(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Read a CSS token so the waveform follows the theme instead of hard-coding slate. */
function token(name: string, fallback: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return raw ? `rgb(${raw.split(/\s+/).join(' ')})` : fallback
}

const SPEEDS = [0.75, 1, 1.25, 1.5]

const WaveformPlayer = forwardRef<WaveformPlayerHandle, WaveformPlayerProps>(
  function WaveformPlayer({ src, peaks, onTimeUpdate, onReady }, ref) {
    const container = useRef<HTMLDivElement>(null)
    const ws = useRef<WaveSurfer | null>(null)
    const loopRegion = useRef<{ start: number; end: number } | null>(null)
    const [ready, setReady] = useState(false)
    const [playing, setPlaying] = useState(false)
    const [looping, setLooping] = useState(false)
    const [speed, setSpeed] = useState(1)
    const [time, setTime] = useState(0)
    const [duration, setDuration] = useState(0)

    useEffect(() => {
      if (!container.current) return
      const instance = WaveSurfer.create({
        container: container.current,
        url: src,
        ...(peaks ? { peaks: [peaks.peaks], duration: peaks.duration } : {}),
        height: 72,
        waveColor: token('--wave', '#cbd5e1'),
        progressColor: token('--wave-played', '#4338ca'),
        cursorColor: token('--ink', '#0f172a'),
        cursorWidth: 1,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        normalize: true,
      })
      ws.current = instance
      setReady(false)

      instance.on('ready', () => {
        setReady(true)
        setDuration(instance.getDuration())
        onReady?.(instance.getDuration())
      })
      instance.on('play', () => setPlaying(true))
      instance.on('pause', () => setPlaying(false))
      instance.on('timeupdate', (t: number) => {
        setTime(t)
        onTimeUpdate?.(t)
        // Looping is done here rather than with the regions plugin: one comparison per
        // tick, no extra bundle, and it survives a seek out of the region.
        const region = loopRegion.current
        if (region && t >= region.end) instance.setTime(region.start)
      })

      return () => {
        ws.current = null
        instance.destroy()
      }
      // onTimeUpdate/onReady are intentionally excluded: they change identity every
      // render and re-creating the waveform would refetch the whole file.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src, peaks])

    useImperativeHandle(ref, () => ({
      seekAndPlay(seconds: number) {
        const instance = ws.current
        if (!instance) return
        loopRegion.current = null
        setLooping(false)
        instance.setTime(seconds)
        void instance.play()
      },
      playPause() {
        void ws.current?.playPause()
      },
      loop(start: number, end: number) {
        const instance = ws.current
        if (!instance) return
        loopRegion.current = { start, end }
        setLooping(true)
        instance.setTime(start)
        void instance.play()
      },
      clearLoop() {
        loopRegion.current = null
        setLooping(false)
      },
      currentTime() {
        return ws.current?.getCurrentTime() ?? 0
      },
    }))

    return (
      <div className="card p-3">
        <div ref={container} className="min-h-[72px]">
          {!ready && <div className="skeleton h-[72px] w-full" />}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <button
            onClick={() => ws.current?.playPause()}
            disabled={!ready}
            aria-label={playing ? 'Tạm dừng' : 'Phát'}
            className="btn-primary h-9 w-9 !px-0"
          >
            {playing ? <Pause /> : <Play />}
          </button>

          <span className="tabular-nums text-muted">
            {clock(time)} <span className="text-faint">/ {ready ? clock(duration) : '—:—'}</span>
          </span>

          {looping && (
            <button
              onClick={() => {
                loopRegion.current = null
                setLooping(false)
              }}
              className="btn-outline btn-sm"
              title="Dừng lặp lượt lời này"
            >
              <Loop className="h-3.5 w-3.5" />
              Đang lặp
            </button>
          )}

          <div className="ml-auto flex items-center gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setSpeed(s)
                  ws.current?.setPlaybackRate(s, true)
                }}
                className={`rounded-md px-2 py-1 text-xs tabular-nums transition-colors ${
                  speed === s
                    ? 'bg-accent text-accent-ink'
                    : 'text-muted hover:bg-sunken hover:text-ink'
                }`}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  },
)

export default WaveformPlayer
