// Corrections → hotwords: the licence-safe way the model's mistakes feed back
// (it may not be fine-tuned, CLAUDE.md rule 8). Nothing is added until someone clicks.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import type { HotwordSuggestion } from '../api/types'

// Dismissals are a per-browser convenience; a dismissed phrase comes back elsewhere.
const DISMISSED_KEY = 'vnstt.hotwordSuggestions.dismissed'

function loadDismissed(): string[] {
  try {
    return JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? '[]') as string[]
  } catch {
    return []
  }
}

function saveDismissed(terms: string[]) {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(terms))
  } catch {
    // private mode: dismissals just aren't remembered
  }
}

export default function HotwordSuggestions({ canAdd }: { canAdd: boolean }) {
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState<string[]>(loadDismissed)
  const suggestions = useQuery({
    queryKey: ['hotword-suggestions'],
    queryFn: () => api.hotwordSuggestions(),
  })
  const add = useMutation({
    mutationFn: (s: HotwordSuggestion) =>
      api.createHotword({
        term: s.term,
        note: `từ ${s.count} chỗ đã sửa, vd. "${s.examples[0]?.heard}" → "${s.examples[0]?.corrected}"`,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hotwords'] })
      queryClient.invalidateQueries({ queryKey: ['hotword-suggestions'] })
    },
  })

  const dismiss = (term: string) => {
    const next = [...dismissed, term]
    setDismissed(next)
    saveDismissed(next)
  }

  const rows = (suggestions.data ?? []).filter((s) => !dismissed.includes(s.term))

  return (
    <div className="mb-6 rounded-xl border border-line bg-surface p-4">
      <h2 className="font-semibold">Gợi ý từ các chỗ đã sửa</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Mỗi khi người duyệt sửa một từ nghe sai, cụm từ đúng được gợi ý ở đây. Thêm vào từ
        khóa để mô hình ưu tiên nó ở các tập chép lời sau — đây là cách mô hình học từ lỗi
        của mình, vì giấy phép không cho phép huấn luyện lại mô hình.
      </p>

      {suggestions.isLoading && <p className="mt-3 text-sm text-faint">Đang tải…</p>}
      {suggestions.isSuccess && rows.length === 0 && (
        <p className="mt-3 text-sm text-faint">
          Chưa có gợi ý nào. Sửa chữ trong một tập (vd. “Zelli” thành “Di Li”) rồi quay lại đây.
        </p>
      )}

      {rows.length > 0 && (
        <ul className="mt-3 divide-y divide-line border-y border-line">
          {rows.map((s) => (
            <li key={s.term} className="flex flex-wrap items-start gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {s.term}{' '}
                  <span className="text-xs font-normal text-faint">· {s.count} lần sửa</span>
                </div>
                <ul className="mt-0.5 space-y-0.5 text-xs text-muted">
                  {s.examples.map((ex, k) => (
                    <li key={k} className="truncate">
                      <span className="line-through decoration-rose-400">{ex.heard}</span>
                      {' → '}
                      <span className="text-ink">{ex.corrected}</span>
                      {' · '}
                      <Link to={`/episodes/${ex.episode_id}`} className="hover:underline">
                        {ex.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex shrink-0 gap-1">
                {canAdd && (
                  <button
                    onClick={() => add.mutate(s)}
                    disabled={add.isPending}
                    className="btn-primary btn-sm disabled:opacity-40"
                  >
                    Thêm
                  </button>
                )}
                <button onClick={() => dismiss(s.term)} className="btn-ghost btn-sm">
                  Bỏ qua
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {add.isError && (
        <p className="mt-2 text-sm text-rose-600">
          {add.error instanceof ApiError ? add.error.detail : 'Không thêm được'}
        </p>
      )}
    </div>
  )
}
