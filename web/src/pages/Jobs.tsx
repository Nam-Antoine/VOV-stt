// PLAN §10: running job with live log tail (poll every 2 s), failed jobs with retry.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { Job } from '../api/types'

const STATUS_STYLE: Record<string, string> = {
  queued: 'bg-amber-100 text-amber-800',
  running: 'bg-blue-100 text-blue-800',
  done: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
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
        <h1 className="text-xl font-semibold">Jobs</h1>
        <span className="text-sm text-slate-500">
          one worker, one episode at a time — {queued} waiting
        </span>
      </header>

      <div className="overflow-hidden rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Kind</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Attempts</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((j) => (
              <tr key={j.id} className="border-t border-slate-100 align-top">
                <td className="px-3 py-2">{j.kind}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[j.status] ?? ''}`}
                  >
                    {j.status}
                  </span>
                  {j.error && (
                    <div className="mt-1 max-w-xl text-xs text-rose-700">{j.error}</div>
                  )}
                </td>
                <td className="px-3 py-2 tabular-nums">
                  {j.attempts} / {j.max_attempts}
                </td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {new Date(j.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => setOpenLog(openLog === j.id ? null : j.id)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                  >
                    {openLog === j.id ? 'hide log' : 'log'}
                  </button>
                  {j.status === 'failed' && (
                    <button
                      onClick={() => retry.mutate(j.id)}
                      className="ml-1 rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                    >
                      retry
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-400">
                  No jobs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {openLog && (
        <pre className="mt-3 max-h-64 overflow-auto rounded border border-slate-200 bg-slate-900 p-3 text-xs text-slate-100">
          {log.data?.log || 'no output yet'}
        </pre>
      )}
    </section>
  )
}
