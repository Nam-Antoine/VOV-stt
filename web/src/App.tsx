import { useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { api, ApiError } from './api/client'
import { Spinner } from './components/Icons'
import ThemeToggle from './components/ThemeToggle'
import Episode from './pages/Episode'
import Episodes from './pages/Episodes'
import Exports from './pages/Exports'
import Hotwords from './pages/Hotwords'
import Jobs from './pages/Jobs'
import Login from './pages/Login'

const NAV = [
  { to: '/episodes', label: 'Episodes' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/hotwords', label: 'Hotwords' },
  { to: '/exports', label: 'Exports' },
]

/** A dead worker is invisible until nothing ever finishes. Surface it in the header. */
function WorkerPulse() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
    retry: false,
  })

  if (!health.data) return null
  const beat = health.data.worker_heartbeat_s
  const stalled = beat === null || beat > 120
  if (!stalled) return null

  return (
    <span
      className="chip bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300"
      title={
        beat === null
          ? 'The worker has never checked in.'
          : `Last worker heartbeat ${Math.round(beat)}s ago.`
      }
    >
      <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
      worker not responding
    </span>
  )
}

export default function App() {
  const queryClient = useQueryClient()

  // One probe decides whether the whole app is reachable. A 401 is a normal answer
  // here, not an error worth retrying.
  const session = useQuery({
    queryKey: ['session'],
    queryFn: () => api.me(),
    retry: false,
  })

  if (session.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted">
        <Spinner className="h-5 w-5" />
      </div>
    )
  }

  const signedIn = session.isSuccess
  const unauthorised = session.error instanceof ApiError && session.error.status === 401

  if (!signedIn && unauthorised) return <Login />
  if (!signedIn) {
    return (
      <div className="mx-auto mt-24 max-w-md px-4">
        <div className="card p-6">
          <h1 className="font-semibold">Cannot reach the API</h1>
          <p className="mt-2 text-sm text-muted">
            The browser reached this page but not the backend. Check the stack is up:
          </p>
          <pre className="mt-3 rounded-lg bg-sunken p-3 text-xs text-ink">make dev</pre>
          <button
            onClick={() => session.refetch()}
            className="btn-outline mt-4"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold leading-tight">
              VN-STT Corpus
            </div>
            <div className="truncate text-xs leading-tight text-faint">
              VOV2 · Đàn bà 30+
            </div>
          </div>

          <div className="ml-2 hidden sm:block">
            <WorkerPulse />
          </div>

          <nav className="ml-auto flex items-center gap-0.5">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `rounded-lg px-2.5 py-1.5 text-sm transition-colors sm:px-3 ${
                    isActive
                      ? 'bg-accent text-accent-ink'
                      : 'text-muted hover:bg-sunken hover:text-ink'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
            <span className="mx-1 h-5 w-px bg-line" />
            <ThemeToggle />
            <button
              onClick={async () => {
                await api.logout()
                queryClient.clear()
              }}
              className="btn-ghost btn-sm"
            >
              Sign out
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/episodes" replace />} />
          <Route path="/episodes" element={<Episodes />} />
          <Route path="/episodes/:id" element={<Episode />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/hotwords" element={<Hotwords />} />
          <Route path="/exports" element={<Exports />} />
          <Route
            path="*"
            element={<p className="text-muted">Not found.</p>}
          />
        </Routes>
      </main>

      <footer className="mx-auto w-full max-w-7xl px-4 pb-8 pt-2 text-xs leading-relaxed text-faint">
        Verbatim corpus — fillers, repetitions and false starts are the data. Engine:
        hynt/Zipformer-30M-RNNT-6000h (CC BY-NC-ND 4.0, non-commercial; see
        LICENSE-NOTICE.md).
      </footer>
    </div>
  )
}
