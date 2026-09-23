import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { api, ApiError } from './api/client'
import { Cycle, Download, Library, Signout, Spinner, Tag, Users as UsersIcon } from './components/Icons'
import ThemeToggle from './components/ThemeToggle'
import Episode from './pages/Episode'
import Episodes from './pages/Episodes'
import Exports from './pages/Exports'
import Hotwords from './pages/Hotwords'
import Jobs from './pages/Jobs'
import Login from './pages/Login'
import Account from './pages/Account'
import Users from './pages/Users'
import type { Me } from './api/types'

const NAV = [
  { to: '/episodes', label: 'Các tập', Icon: Library },
  { to: '/jobs', label: 'Tác vụ', Icon: Cycle },
  { to: '/hotwords', label: 'Từ khóa', Icon: Tag },
  { to: '/exports', label: 'Xuất file', Icon: Download },
]
const ADMIN_NAV = [{ to: '/users', label: 'Tài khoản', Icon: UsersIcon }]

/** Who is signed in; links to the Account page (change password). */
function AccountLink({ me, compact = false }: { me: Me; compact?: boolean }) {
  const name = me.display_name || me.username
  return (
    <Link
      to="/account"
      className="flex min-w-0 items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-sunken"
      title="Tài khoản của bạn — đổi mật khẩu"
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-sunken text-xs font-semibold uppercase text-ink">
        {name.slice(0, 1)}
      </span>
      {!compact && (
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-sm font-medium text-ink">{name}</span>
          <span className="block text-xs text-faint">{me.role === 'admin' ? 'Quản trị viên' : 'Biên tập viên'}</span>
        </span>
      )}
    </Link>
  )
}

function SignOutButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="btn-ghost btn-sm" aria-label="Đăng xuất" title="Đăng xuất">
      <Signout className="h-4 w-4" />
    </button>
  )
}

function Wordmark() {
  return (
    <Link to="/" className="inline-flex shrink-0" title="Kho ngữ liệu VN-STT — Đàn bà 30+">
      <img src="/favicon.svg" alt="VN-STT" width={36} height={36} className="h-9 w-9" />
    </Link>
  )
}

/**
 * The lime card at the foot of the sidebar. The reference uses the slot for an upsell;
 * here it carries the one number the team works towards — hours verified.
 */
function CorpusCard() {
  const stats = useQuery({ queryKey: ['stats'], queryFn: () => api.stats(), refetchInterval: 60_000 })
  const hours = (h: number) => h.toLocaleString('vi-VN', { maximumFractionDigits: 1 })
  return (
    <div className="rounded-xl bg-accent p-4 text-accent-ink">
      <p className="text-sm font-medium leading-snug">
        {stats.data
          ? `${hours(stats.data.hours_verified)} / ${hours(stats.data.hours_transcribed)} giờ đã được duyệt`
          : 'Kho ngữ liệu nguyên văn'}
      </p>
      <Link
        to="/exports"
        className="mt-3 inline-flex rounded-md bg-ink px-2.5 py-1.5 text-xs font-medium text-canvas transition-opacity hover:opacity-85 dark:bg-[#111] dark:text-[#f0f0f0]"
      >
        Tải bản chép lời
      </Link>
    </div>
  )
}

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
      className="chip bg-[#f3dcd3] text-[#8a2d17] dark:bg-[#3a1f17] dark:text-[#f0b39c]"
      title={
        beat === null
          ? 'Tiến trình xử lý chưa từng báo hoạt động.'
          : `Tín hiệu gần nhất từ tiến trình xử lý: ${Math.round(beat)} giây trước.`
      }
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#b5402a]" />
      Tiến trình xử lý không phản hồi
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
          <h1 className="font-semibold">Không kết nối được máy chủ</h1>
          <p className="mt-2 text-sm text-muted">
            Trình duyệt tải được trang này nhưng không kết nối được backend. Kiểm tra hệ thống đã chạy chưa:
          </p>
          <pre className="mt-3 rounded-lg bg-sunken p-3 text-xs text-ink">make dev</pre>
          <button
            onClick={() => session.refetch()}
            className="btn-outline mt-4"
          >
            Thử lại
          </button>
        </div>
      </div>
    )
  }

  const me = session.data
  // With login switched off (the default) there are no accounts: no Users page, no
  // account link, no sign-out.
  const accounts = me.auth_enabled
  const nav = accounts && me.role === 'admin' ? [...NAV, ...ADMIN_NAV] : NAV

  const signOut = async () => {
    await api.logout()
    queryClient.clear()
  }

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop: a fixed sidebar, as in the reference. */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface px-5 py-6 lg:flex">
        <Wordmark />

        <nav className="mt-10 space-y-1">
          {nav.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-accent font-medium text-accent-ink'
                    : 'text-muted hover:bg-sunken hover:text-ink'
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="my-6 h-px bg-line" />
        <WorkerPulse />

        <div className="mt-auto space-y-4">
          <CorpusCard />
          <div className="flex items-center gap-1 border-t border-line pt-4">
            {accounts && <AccountLink me={me} />}
            <div className="ml-auto flex shrink-0 items-center">
              <ThemeToggle />
              {accounts && <SignOutButton onClick={signOut} />}
            </div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phones and tablets: wordmark row, then the nav as a scrollable pill row. */}
        <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur lg:hidden">
          <div className="flex items-center gap-2 px-4 pt-3">
            <Wordmark />
            <div className="ml-2"><WorkerPulse /></div>
            <div className="ml-auto flex items-center">
              {accounts && <AccountLink me={me} compact />}
              <ThemeToggle />
              {accounts && <SignOutButton onClick={signOut} />}
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 py-2">
            {nav.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition-colors ${
                    isActive ? 'bg-accent font-medium text-accent-ink' : 'text-muted hover:text-ink'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8 lg:py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/episodes" replace />} />
            <Route path="/episodes" element={<Episodes />} />
            <Route path="/episodes/:id" element={<Episode />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/hotwords" element={<Hotwords />} />
            <Route path="/exports" element={<Exports />} />
            {accounts && <Route path="/account" element={<Account />} />}
            <Route
              path="/users"
              element={accounts && me.role === 'admin' ? <Users /> : <Navigate to="/episodes" replace />}
            />
            <Route
              path="*"
              element={<p className="text-muted">Không tìm thấy trang.</p>}
            />
          </Routes>
        </main>

        <footer className="mx-auto w-full max-w-6xl px-4 pb-8 text-xs leading-relaxed text-faint sm:px-8">
          <div className="border-t border-line pt-4">
          Kho ngữ liệu nguyên văn — từ đệm, lặp từ và chỗ nói vấp chính là dữ liệu. Mô hình:
          hynt/Zipformer-30M-RNNT-6000h (CC BY-NC-ND 4.0, phi thương mại; xem
          LICENSE-NOTICE.md).
          </div>
        </footer>
      </div>
    </div>
  )
}
