// Downloads: the punctuated reading copy — a title, then paragraphs of whole sentences
// (~80 words; a pause over 1.5 s always starts one), no speaker labels. One button opens a menu of the
// three formats.
//
// The verbatim corpus formats (json, csv, srt, eaf…) still exist at
// /api/episodes/{id}/export.{fmt}; they are not offered here because the engine writes
// them in capitals without punctuation, which is not what anyone reading wants.
import { useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import { Chevron, Download } from './Icons'

const FORMATS = [
  { fmt: 'readable.docx', label: 'Word (.docx)', hint: 'Mở và sửa được trong Word' },
  { fmt: 'readable.pdf', label: 'PDF', hint: 'Để in hoặc gửi đi, không sửa được' },
  { fmt: 'readable.txt', label: 'Văn bản (.txt)', hint: 'Chữ thuần, mỗi đoạn một dòng' },
]

/** One episode's downloads; without ``episodeId`` it zips every finished episode. */
export default function ExportMenu({
  episodeId,
  disabled = false,
  disabledReason,
  label = 'Tải về',
}: {
  episodeId?: string
  disabled?: boolean
  /** Tooltip while disabled: why the download isn't available yet. */
  disabledReason?: string
  label?: string
}) {
  const href = (fmt: string) => (episodeId ? api.exportUrl(episodeId, fmt) : api.allZipUrl(fmt))
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
    <div
      ref={wrap}
      className={`relative inline-flex items-center ${disabled ? 'pointer-events-none opacity-50' : ''}`}
      title={disabled ? disabledReason : undefined}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        className="btn-primary"
      >
        <Download className="h-3.5 w-3.5" />
        {label}
        <Chevron className={`h-4 w-4 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-1 w-60 animate-slide-up overflow-hidden rounded-xl border border-line bg-surface text-left shadow-lg"
        >
          {FORMATS.map((f) => (
            <a
              key={f.fmt}
              role="menuitem"
              href={href(f.fmt)}
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
