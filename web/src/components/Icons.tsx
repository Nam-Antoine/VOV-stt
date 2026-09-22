// A handful of inline icons. Deliberately not an icon package: this app needs nine
// glyphs and an icon dependency would outweigh the entire UI bundle.
import type { ReactNode } from 'react'

type P = { className?: string }

const base = 'h-4 w-4'

function Svg({ className, children }: P & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className ?? base}
    >
      {children}
    </svg>
  )
}

export const Play = (p: P) => (
  <Svg {...p}>
    <path d="M6 4.5v15l13-7.5z" fill="currentColor" stroke="none" />
  </Svg>
)
export const Pause = (p: P) => (
  <Svg {...p}>
    <path d="M7 4.5v15M17 4.5v15" />
  </Svg>
)
export const Loop = (p: P) => (
  <Svg {...p}>
    <path d="M17 2l4 4-4 4" />
    <path d="M3 11V9a4 4 0 014-4h14" />
    <path d="M7 22l-4-4 4-4" />
    <path d="M21 13v2a4 4 0 01-4 4H3" />
  </Svg>
)
export const Upload = (p: P) => (
  <Svg {...p}>
    <path d="M12 16V4m0 0L8 8m4-4l4 4" />
    <path d="M3 16v2a3 3 0 003 3h12a3 3 0 003-3v-2" />
  </Svg>
)
export const Download = (p: P) => (
  <Svg {...p}>
    <path d="M12 4v12m0 0l-4-4m4 4l4-4" />
    <path d="M3 16v2a3 3 0 003 3h12a3 3 0 003-3v-2" />
  </Svg>
)
export const Sun = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Svg>
)
export const Moon = (p: P) => (
  <Svg {...p}>
    <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
  </Svg>
)
export const Search = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </Svg>
)
export const Chevron = (p: P) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
)
export const Keyboard = (p: P) => (
  <Svg {...p}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8" />
  </Svg>
)
export const Spinner = ({ className }: P) => (
  <svg viewBox="0 0 24 24" className={`${className ?? base} animate-spin`} aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5"
            fill="none" opacity="0.25" />
    <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" fill="none" />
  </svg>
)
