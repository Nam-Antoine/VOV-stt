// A handful of inline icons. Deliberately not an icon package: this app needs a
// score of glyphs and an icon dependency would outweigh the entire UI bundle.
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

// Sidebar navigation and the three-step upload header.
export const Library = (p: P) => (
  <Svg {...p}>
    <path d="M9 18V5l12-2v13" />
    <circle cx="6" cy="18" r="3" />
    <circle cx="18" cy="16" r="3" />
  </Svg>
)
export const Cycle = (p: P) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 01-15.5 6.2L3 16" />
    <path d="M3 21v-5h5" />
    <path d="M3 12a9 9 0 0115.5-6.2L21 8" />
    <path d="M21 3v5h-5" />
  </Svg>
)
export const Tag = (p: P) => (
  <Svg {...p}>
    <path d="M20.6 13.4l-7.2 7.2a2 2 0 01-2.8 0L3 13V3h10l7.6 7.6a2 2 0 010 2.8z" />
    <circle cx="7.5" cy="7.5" r="1.25" fill="currentColor" stroke="none" />
  </Svg>
)
export const ArrowLeft = (p: P) => (
  <Svg {...p}>
    <path d="M19 12H5m0 0l6-6m-6 6l6 6" />
  </Svg>
)
export const CloudUpload = (p: P) => (
  <Svg {...p}>
    <path d="M7 18a5 5 0 01-.9-9.9A6 6 0 0117.7 7 4.5 4.5 0 0117.5 18" />
    <path d="M12 21v-9m0 0l-3.5 3.5M12 12l3.5 3.5" />
  </Svg>
)
export const Waveform = (p: P) => (
  <Svg {...p}>
    <path d="M3 12h2M7 8v8M11 4v16M15 7v10M19 10v4M21 12h0" />
  </Svg>
)
export const Signout = (p: P) => (
  <Svg {...p}>
    <path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" />
    <path d="M10 17l-5-5 5-5M5 12h11" />
  </Svg>
)
export const Users = (p: P) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M2.5 20a6.5 6.5 0 0113 0" />
    <path d="M16 4.6a3.5 3.5 0 010 6.8M18.5 20a6.5 6.5 0 00-3-5.5" />
  </Svg>
)
