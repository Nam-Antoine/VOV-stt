// wavesurfer.js player (PLAN §6, §10). Pinned to the top of the Episode screen.
//
// The one interaction that matters: seek to a word's start and play from there, within
// ~200 ms of the true onset (PLAN §2.2). Word `end` is the next word's start, so the
// player must seek on `start` and never try to be cleverer about the boundary.

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'

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

const WaveformPlayer = forwardRef<WaveformPlayerHandle, WaveformPlayerProps>(
  function WaveformPlayer({ src, onTimeUpdate, onReady }, ref) {
    const container = useRef<HTMLDivElement>(null)
    const [ready, setReady] = useState(false)

    // TODO(T4): create the WaveSurfer instance here.
    //   const ws = WaveSurfer.create({ container: container.current!, url: src,
    //     height: 96, waveColor: '#cbd5e1', progressColor: '#0f172a', normalize: true })
    //   ws.on('ready', () => { setReady(true); onReady?.(ws.getDuration()) })
    //   ws.on('timeupdate', (t) => onTimeUpdate?.(t))
    //   A 15-minute WAV is ~28 MB: use a pre-decoded peaks array from the backend if
    //   first paint is slow, rather than downloading the file twice.
    useEffect(() => {
      return () => {
        // ws.destroy()
      }
    }, [src])

    useImperativeHandle(ref, () => ({
      seekAndPlay() {
        // TODO(T4): ws.setTime(seconds); ws.play()
      },
      playPause() {
        // TODO(T4): ws.playPause()
      },
      loop() {
        // TODO(T4): set a region and re-seek on 'timeupdate' past `end`
      },
      clearLoop() {
        // TODO(T4)
      },
      currentTime() {
        return 0
      },
    }))

    return (
      <div className="sticky top-0 z-10 rounded border border-slate-200 bg-white p-3">
        <div ref={container} className="min-h-[96px]" />
        {!ready && (
          <p className="text-xs text-slate-400">
            Waveform player — T4. Wire wavesurfer to {src} here.
          </p>
        )}
      </div>
    )
  },
)

export default WaveformPlayer
