// PLAN §10: running job with live log tail (poll every 2 s), failed jobs with retry.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import { JOB_KIND_LABEL, JOB_STATUS_LABEL } from '../labels'
import type { Job } from '../api/types'

const STATUS_STYLE: Record<string, string> = {
  queued: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  done: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  failed: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

export default function Jobs() {
  const queryClient = useQueryClient()
  const [openLog, setOpenLog] = useState<string | null>(null)

  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: () => api.listJobs(),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((j: Job) => ['queued', 'running'].includes(j.status))
        ? 2000
        : false,
  })

  const log = useQuery({
    queryKey: ['job-log', openLog],
    queryFn: () => api.jobLog(openLog!),
    enabled: !!openLog,
    refetchInterval: 2000,
  })

  const retry = useMutation({
    mutationFn: (jobId: string) => api.retryJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })

  const rows = jobs.data ?? []
  const queued = rows.filter((j) => j.status === 'queued').length

  return (
    <section>
      <header className="mb-4 flex items-baseline gap-3">
        <h1 className="title">Tác vụ</h1>
        <span className="text-sm text-muted">
          một tiến trình, xử lý từng tập một — {queued} đang chờ
        </span>
      </header>

      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-sunken text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Loại</th>
              <th className="px-3 py-2">Trạng thái</th>
              <th className="px-3 py-2">Số lần thử</th>
              <th className="px-3 py-2">Tạo lúc</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((j) => (
              <tr key={j.id} className="border-t border-line align-top">
                <td className="px-3 py-2">{JOB_KIND_LABEL[j.kind] ?? j.kind}</td>
                <td className="px-3 py-2">
                  <span
                    className={`chip ${STATUS_STYLE[j.status] ?? ''}`}
                  >
                    {JOB_STATUS_LABEL[j.status] ?? j.status}
                  </span>
                  {j.error && (
                    <div className="mt-1 max-w-xl text-xs text-rose-700">{j.error}</div>
                  )}
                </td>
                <td className="px-3 py-2 tabular-nums">
                  {j.attempts} / {j.max_attempts}
                </td>
                <td className="px-3 py-2 text-xs text-muted">
                  {new Date(j.created_at).toLocaleString('vi-VN')}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => setOpenLog(openLog === j.id ? null : j.id)}
                    className="btn-outline btn-sm"
                  >
                    {openLog === j.id ? 'Ẩn nhật ký' : 'Nhật ký'}
                  </button>
                  {j.status === 'failed' && (
                    <button
                      onClick={() => retry.mutate(j.id)}
                      className="btn-outline btn-sm ml-1"
                    >
                      Thử lại
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-faint">
                  Chưa có tác vụ nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* The log pane is deliberately dark in both themes: it is terminal output. */}
      {openLog && (
        <pre className="mt-3 max-h-64 overflow-auto rounded-xl border border-line bg-slate-900 p-3 text-xs text-slate-100">
          {log.data?.log || 'chưa có nội dung'}
        </pre>
      )}
    </section>
  )
}
