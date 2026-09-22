// wavesurfer.js player (PLAN §6, §10). Pinned to the top of the Episode screen.
//
// The one interaction that matters: seek to a word's start and play from there, within
// ~200 ms of the true onset (PLAN §2.2). Word `end` is the next word's start, so the
// player seeks on `start` and never tries to be cleverer about the boundary.

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'

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
  /** api.audioUrl(transcriptId) — range-request streaming of the 16 kHz WAV. */
  src: string
  onTimeUpdate?: (seconds: number) => void
  onReady?: (duration: number) => void
}

function clock(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

const WaveformPlayer = forwardRef<WaveformPlayerHandle, WaveformPlayerProps>(
  function WaveformPlayer({ src, onTimeUpdate, onReady }, ref) {
    const container = useRef<HTMLDivElement>(null)
    const ws = useRef<WaveSurfer | null>(null)
    const loopRegion = useRef<{ start: number; end: number } | null>(null)
    const [ready, setReady] = useState(false)
    const [playing, setPlaying] = useState(false)
    const [time, setTime] = useState(0)
    const [duration, setDuration] = useState(0)

    useEffect(() => {
      if (!container.current) return
      const instance = WaveSurfer.create({
        container: container.current,
        url: src,
        height: 88,
        waveColor: '#cbd5e1',
        progressColor: '#0f172a',
        cursorColor: '#0f172a',
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
    }, [src])

    useImperativeHandle(ref, () => ({
      seekAndPlay(seconds: number) {
        const instance = ws.current
        if (!instance) return
        loopRegion.current = null
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
        instance.setTime(start)
        void instance.play()
      },
      clearLoop() {
        loopRegion.current = null
      },
      currentTime() {
        return ws.current?.getCurrentTime() ?? 0
      },
    }))

    return (
      <div className="sticky top-0 z-10 rounded border border-slate-200 bg-white p-3">
        <div ref={container} className="min-h-[88px]" />
        <div className="mt-2 flex items-center gap-3 text-sm">
          <button
            onClick={() => ws.current?.playPause()}
            disabled={!ready}
            className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-40"
          >
            {playing ? 'Pause' : 'Play'}
          </button>
          <button
            onClick={() => {
              loopRegion.current = null
            }}
            className="rounded border border-slate-300 px-2 py-1 text-xs"
          >
            Clear loop
          </button>
          <span className="tabular-nums text-slate-500">
            {clock(time)} / {ready ? clock(duration) : '…'}
          </span>
        </div>
      </div>
    )
  },
)

export default WaveformPlayer
