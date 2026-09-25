// Per-episode downloads: the punctuated reading copy as Word, PDF or TXT.
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import ExportMenu from '../components/ExportMenu'

export default function Exports() {
  const episodes = useQuery({ queryKey: ['episodes', ''], queryFn: () => api.listEpisodes() })
  const rows = (episodes.data ?? []).filter((e) => e.current_transcript_id)
  // Shares the sidebar's health poll. Without the punctuation model every download 503s.
  const health = useQuery({ queryKey: ['health'], queryFn: () => api.health(), retry: false })
  const noModel = health.data?.readable_available === false
  const NO_MODEL = 'Máy chủ chưa cài mô hình thêm dấu câu'

  return (
    <section>
      <header className="mb-6 flex flex-wrap items-end gap-3">
        <div>
          <h1 className="title">Xuất file</h1>
          <p className="mt-1.5 text-sm text-muted">
            Bản có dấu câu, chia đoạn theo câu.
          </p>
        </div>
        <div className="sm:ml-auto">
          <ExportMenu
            label="Tải tất cả"
            disabled={rows.length === 0 || noModel}
            disabledReason={noModel ? NO_MODEL : 'Chưa có tập nào được chép lời'}
          />
        </div>
      </header>

      {/* Not overflow-hidden: the download menu of the last row must be able to hang below. */}
      <div className="rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-muted [&_th:first-child]:rounded-tl-xl [&_th:last-child]:rounded-tr-xl [&_th]:bg-sunken">
            <tr>
              <th className="px-3 py-2">Tập</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-t border-line">
                <td className="px-3 py-2">
                  <Link to={`/episodes/${e.id}`} className="hover:underline">
                    {e.title || e.slug}
                  </Link>
                </td>
                <td className="px-3 py-2 text-right">
                  <ExportMenu
                    episodeId={e.id}
                    disabled={noModel}
                    disabledReason={NO_MODEL}
                  />
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={2} className="px-3 py-8 text-center text-faint">
                  Chưa có tập nào được chép lời.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
