// PLAN §10: CRUD + "re-run affected episodes".
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'

export default function Hotwords() {
  const queryClient = useQueryClient()
  const [term, setTerm] = useState('')
  const [weight, setWeight] = useState(1.0)
  const [note, setNote] = useState('')

  const hotwords = useQuery({ queryKey: ['hotwords'], queryFn: () => api.listHotwords() })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['hotwords'] })

  const create = useMutation({
    mutationFn: () => api.createHotword({ term, weight, note: note || undefined }),
    onSuccess: () => {
      setTerm('')
      setNote('')
      invalidate()
    },
  })
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.patchHotword(id, { active }),
    onSuccess: invalidate,
  })
  const rerun = useMutation({ mutationFn: () => api.rerunAll() })

  const rows = hotwords.data ?? []

  return (
    <section>
      <header className="mb-4 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Hotwords</h1>
        <span className="text-sm text-slate-500">
          contextual biasing — stored exactly as typed, diacritics included
        </span>
        <button
          onClick={() => rerun.mutate()}
          className="ml-auto rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          title="Only touches episodes with no verified utterances"
        >
          {rerun.isPending ? 'Queueing…' : 'Re-run affected episodes'}
        </button>
      </header>

      {rerun.isSuccess && (
        <p className="mb-3 rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          Queued {rerun.data.length} episode(s). Episodes with verified utterances were
          skipped — a re-run never discards human work.
        </p>
      )}

      <form
        className="mb-4 flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-white p-3"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <label className="text-sm">
          <span className="block text-xs text-slate-500">Term</span>
          <input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            placeholder="Thanh Huyền"
            className="w-56 rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs text-slate-500">Weight</span>
          <input
            type="number"
            step="0.1"
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            className="w-24 rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="flex-1 text-sm">
          <span className="block text-xs text-slate-500">Note</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <button
          type="submit"
          disabled={!term || create.isPending}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          Add
        </button>
        {create.isError && (
          <p className="w-full text-sm text-rose-600">
            {create.error instanceof ApiError ? create.error.detail : 'Failed'}
          </p>
        )}
      </form>

      <div className="overflow-hidden rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Term</th>
              <th className="px-3 py-2">Weight</th>
              <th className="px-3 py-2">Note</th>
              <th className="px-3 py-2">Active</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium">{h.term}</td>
                <td className="px-3 py-2 tabular-nums">{h.weight}</td>
                <td className="px-3 py-2 text-slate-500">{h.note}</td>
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={h.active}
                    onChange={(e) => toggle.mutate({ id: h.id, active: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Hotwords require modified_beam_search decoding; greedy ignores them silently
        (CLAUDE.md rule 5). The pipeline records the sha256 of the term list that
        produced each transcript.
      </p>
    </section>
  )
}
