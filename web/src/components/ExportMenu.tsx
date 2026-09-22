// Seven export formats, one of which is the one people actually want.
//
// The client's deliverable is a Word document, so .docx is a primary button and the
// other six live behind a menu. A row of seven equal buttons made the common case as
// hard to find as ELAN XML.
import { useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import { Chevron, Download } from './Icons'

const PRIMARY = { fmt: 'docx', label: 'Word (.docx)' }

const SECONDARY = [
  { fmt: 'txt', label: 'Plain text', hint: 'one line per utterance' },
  { fmt: 'verified.json', label: 'Verified JSON', hint: 'human layer applied' },
  { fmt: 'json', label: 'Raw JSON', hint: 'engine output, immutable' },
  { fmt: 'csv', label: 'Word CSV', hint: 'per word, with timings' },
  { fmt: 'srt', label: 'Subtitles', hint: 'SubRip' },
  { fmt: 'eaf', label: 'ELAN', hint: 'annotation tiers' },
]

export default function ExportMenu({ episodeId }: { episodeId: string }) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={wrap} className="relative flex items-center">
      <a
        href={api.exportUrl(episodeId, PRIMARY.fmt)}
        className="btn-primary rounded-r-none"
        download
      >
        <Download className="h-3.5 w-3.5" />
        {PRIMARY.label}
      </a>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Other export formats"
        className="btn-primary rounded-l-none border-l border-accent-ink/20 !px-1.5"
      >
        <Chevron className={`h-4 w-4 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-1 w-60 animate-slide-up overflow-hidden rounded-xl border border-line bg-surface shadow-lg"
        >
          {SECONDARY.map((f) => (
            <a
              key={f.fmt}
              role="menuitem"
              href={api.exportUrl(episodeId, f.fmt)}
              download
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-sm hover:bg-sunken"
            >
              <span className="block font-medium">{f.label}</span>
              <span className="block text-xs text-faint">{f.hint}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
