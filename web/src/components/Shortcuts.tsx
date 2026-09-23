// The shortcuts are what make verification fast, and a line of 11px grey text at the
// top of the page is not where anyone finds them. `?` opens this.
import { useEffect } from 'react'

import { Keyboard } from './Icons'

const KEYS: [string, string][] = [
  ['Space', 'Phát / tạm dừng'],
  ['[  ]', 'Lượt lời trước / sau'],
  ['L', 'Lặp lại lượt lời hiện tại'],
  ['F', 'Tự cuộn theo vị trí đang phát'],
  ['Nhấp đúp', 'Sửa một lượt lời'],
  ['Nhấp vào một từ', 'Phát từ từ đó'],
  ['Esc', 'Hủy chỉnh sửa đang làm'],
  ['⌘/Ctrl + Enter', 'Lưu chỉnh sửa'],
  ['?', 'Danh sách này'],
]

export default function Shortcuts({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Phím tắt"
    >
      <div
        className="w-full max-w-sm animate-slide-up rounded-xl border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="flex items-center gap-2 font-semibold">
          <Keyboard />
          Phím tắt
        </h2>
        <dl className="mt-3 space-y-1.5 text-sm">
          {KEYS.map(([key, what]) => (
            <div key={key} className="flex items-baseline gap-3">
              <dt className="w-32 shrink-0">
                <kbd className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono text-xs">
                  {key}
                </kbd>
              </dt>
              <dd className="text-muted">{what}</dd>
            </div>
          ))}
        </dl>
        <button onClick={onClose} className="btn-outline mt-4 w-full">
          Đóng
        </button>
      </div>
    </div>
  )
}
