// PLAN §9: per-episode exports and the corpus zip.
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api } from '../api/client'

const FORMATS = [
  { fmt: 'docx', label: '.docx' },
  { fmt: 'txt', label: '.txt' },
  { fmt: 'verified.json', label: 'verified.json' },
  { fmt: 'json', label: 'raw.json' },
  { fmt: 'csv', label: '.csv' },
  { fmt: 'srt', label: '.srt' },
  { fmt: 'eaf', label: '.eaf' },
]

export default function Exports() {
  const episodes = useQuery({ queryKey: ['episodes', ''], queryFn: () => api.listEpisodes() })
  const rows = (episodes.data ?? []).filter((e) => e.current_transcript_id)

  return (
    <section>
      <header className="mb-4 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Exports</h1>
        <span className="text-sm text-muted">
          always regenerated from the raw JSON — nothing cached
        </span>
      </header>

      <div className="mb-5 flex gap-2">
        <a
          href={api.corpusZipUrl('verified')}
          className="btn-primary"
        >
          corpus.zip (verified)
        </a>
        <a
          href={api.corpusZipUrl('all')}
          className="btn-outline"
        >
          corpus.zip (all)
        </a>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-sunken text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Episode</th>
              <th className="px-3 py-2">Formats</th>
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
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {FORMATS.map((f) => (
                      <a
                        key={f.fmt}
                        href={api.exportUrl(e.id, f.fmt)}
                        className="btn-outline btn-sm"
                      >
                        {f.label}
                      </a>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={2} className="px-3 py-8 text-center text-faint">
                  No transcribed episodes yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
