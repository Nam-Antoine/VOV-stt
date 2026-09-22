import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import Episode from './pages/Episode'
import Episodes from './pages/Episodes'
import Exports from './pages/Exports'
import Hotwords from './pages/Hotwords'
import Jobs from './pages/Jobs'

const NAV = [
  { to: '/episodes', label: 'Episodes' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/hotwords', label: 'Hotwords' },
  { to: '/exports', label: 'Exports' },
]

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
          <span className="font-semibold">VN-STT Corpus</span>
          <span className="text-sm text-slate-500">VOV2 · Đàn bà 30+</span>
          <nav className="ml-auto flex gap-1">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm ${
                    isActive ? 'bg-slate-900 text-white' : 'hover:bg-slate-100'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/episodes" replace />} />
          <Route path="/episodes" element={<Episodes />} />
          <Route path="/episodes/:id" element={<Episode />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/hotwords" element={<Hotwords />} />
          <Route path="/exports" element={<Exports />} />
          <Route path="*" element={<p className="text-slate-500">Not found.</p>} />
        </Routes>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-400">
        Verbatim corpus — fillers, repetitions and false starts are the data. Engine:
        hynt/Zipformer-30M-RNNT-6000h (CC BY-NC-ND 4.0, non-commercial; see
        LICENSE-NOTICE.md).
      </footer>
    </div>
  )
}
