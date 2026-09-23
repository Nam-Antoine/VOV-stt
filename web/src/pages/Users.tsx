// Admins create accounts, reset passwords, change roles and lock accounts. Accounts are
// never deleted: edit history records usernames and must keep pointing at someone.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import { useMe } from '../api/session'
import type { Role, User } from '../api/types'

const ROLE_LABEL: Record<Role, string> = { admin: 'Quản trị viên', editor: 'Biên tập viên' }

const errorText = (e: unknown) => (e instanceof ApiError ? e.detail : 'Thất bại')

function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

/** Readable and strong enough: 16 chars from an alphabet without look-alikes. */
function generatePassword() {
  const abc = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => abc[b % abc.length]).join('')
}

function CreateUser() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<Role>('editor')
  const [password, setPassword] = useState(generatePassword)

  const create = useMutation({
    mutationFn: () =>
      api.createUser({ username: username.trim().toLowerCase(), display_name: displayName || undefined, role, password }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  const reset = () => {
    setUsername('')
    setDisplayName('')
    setRole('editor')
    setPassword(generatePassword())
    create.reset()
  }

  if (create.isSuccess) {
    return (
      <div className="card mb-6 p-4 text-sm">
        <p>
          Đã tạo tài khoản <b className="font-semibold">{create.data.username}</b>. Gửi thông tin
          này cho người dùng — mật khẩu sẽ không hiển thị lại:
        </p>
        <pre className="mt-3 select-all rounded-lg bg-sunken p-3 text-xs text-ink">
          {`Địa chỉ: ${window.location.origin}\nTên đăng nhập: ${create.data.username}\nMật khẩu: ${password}`}
        </pre>
        <p className="mt-2 text-xs text-muted">Họ có thể đổi mật khẩu trong mục Tài khoản sau khi đăng nhập.</p>
        <button onClick={reset} className="btn-outline btn-sm mt-3">Tạo tài khoản khác</button>
      </div>
    )
  }

  return (
    <form
      className="card mb-6 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto_1fr_auto] lg:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate()
      }}
    >
      <label className="block text-sm">
        <span className="text-muted">Tên đăng nhập</span>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="vd. lan.nguyen"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoComplete="off"
          pattern="[a-zA-Z0-9][a-zA-Z0-9._\-]{1,31}"
          title="2–32 ký tự: chữ không dấu, số, dấu chấm, gạch dưới, gạch ngang"
          className="field mt-1"
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted">Họ tên</span>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Nguyễn Thị Lan"
          className="field mt-1"
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted">Vai trò</span>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)} className="field mt-1">
          <option value="editor">{ROLE_LABEL.editor}</option>
          <option value="admin">{ROLE_LABEL.admin}</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="text-muted">Mật khẩu ban đầu</span>
        <div className="mt-1 flex gap-1">
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            spellCheck={false}
            className="field min-w-0 font-mono"
          />
          <button type="button" onClick={() => setPassword(generatePassword())} className="btn-ghost btn-sm" title="Tạo mật khẩu ngẫu nhiên">
            ↻
          </button>
        </div>
      </label>
      <button type="submit" disabled={!username.trim() || !password || create.isPending} className="btn-primary">
        {create.isPending ? 'Đang tạo…' : 'Tạo tài khoản'}
      </button>
      {create.isError && (
        <p className="text-sm text-rose-600 dark:text-rose-400 sm:col-span-2 lg:col-span-5" role="alert">
          {errorText(create.error)}
        </p>
      )}
    </form>
  )
}

function UserRow({ user, isMe }: { user: User; isMe: boolean }) {
  const queryClient = useQueryClient()
  const [newPassword, setNewPassword] = useState<string | null>(null)
  const update = useMutation({
    mutationFn: (patch: Parameters<typeof api.updateUser>[1]) => api.updateUser(user.id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  const resetPassword = () => {
    const pw = generatePassword()
    if (!confirm(`Đặt lại mật khẩu cho ${user.username}? Người này sẽ bị đăng xuất khỏi mọi thiết bị.`)) return
    update.mutate({ password: pw }, { onSuccess: () => setNewPassword(pw) })
  }

  const rename = () => {
    const name = prompt('Họ tên hiển thị', user.display_name ?? '')
    if (name !== null) update.mutate({ display_name: name })
  }

  return (
    <tr className={`border-t border-line align-top ${user.is_active ? '' : 'opacity-60'}`}>
      <td className="px-3 py-2.5">
        <div className="font-medium">
          {user.username}
          {isMe && <span className="ml-1.5 text-xs font-normal text-faint">(bạn)</span>}
        </div>
        <button onClick={rename} className="text-xs text-muted hover:text-ink hover:underline">
          {user.display_name || 'Thêm họ tên'}
        </button>
      </td>
      <td className="px-3 py-2.5">
        <select
          value={user.role}
          disabled={isMe || update.isPending}
          onChange={(e) => update.mutate({ role: e.target.value as Role })}
          className="field py-1 text-sm"
          title={isMe ? 'Không thể tự đổi vai trò của mình' : undefined}
        >
          <option value="editor">{ROLE_LABEL.editor}</option>
          <option value="admin">{ROLE_LABEL.admin}</option>
        </select>
      </td>
      <td className="px-3 py-2.5 text-muted tabular-nums">{when(user.last_login_at)}</td>
      <td className="px-3 py-2.5">
        {user.is_active ? (
          <span className="chip bg-verified/15 text-ink">Đang hoạt động</span>
        ) : (
          <span className="chip bg-sunken text-muted">Đã khoá</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right">
        <div className="flex flex-wrap justify-end gap-1">
          <button onClick={resetPassword} disabled={update.isPending} className="btn-ghost btn-sm">
            Đặt lại mật khẩu
          </button>
          {!isMe && (
            <button
              onClick={() => update.mutate({ is_active: !user.is_active })}
              disabled={update.isPending}
              className="btn-ghost btn-sm"
            >
              {user.is_active ? 'Khoá' : 'Mở khoá'}
            </button>
          )}
        </div>
        {newPassword && (
          <p className="mt-1 text-left text-xs sm:text-right">
            Mật khẩu mới: <code className="select-all rounded bg-sunken px-1.5 py-0.5 text-ink">{newPassword}</code>
          </p>
        )}
        {update.isError && (
          <p className="mt-1 text-xs text-rose-600 dark:text-rose-400" role="alert">{errorText(update.error)}</p>
        )}
      </td>
    </tr>
  )
}

export default function Users() {
  const me = useMe()
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() })

  return (
    <section>
      <header className="mb-6">
        <p className="eyebrow">Quản trị</p>
        <h1 className="title mt-1">Tài khoản</h1>
        <p className="mt-1.5 max-w-xl text-sm text-muted">
          Biên tập viên duyệt, sửa và xuất bản chép lời. Quản trị viên làm được mọi việc đó, và
          thêm: quản lý tài khoản, từ khóa, và xoá tập. Tài khoản không bị xoá, chỉ bị khoá, để lịch
          sử chỉnh sửa luôn biết ai đã sửa.
        </p>
      </header>

      <CreateUser />

      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="bg-sunken text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Tài khoản</th>
              <th className="px-3 py-2">Vai trò</th>
              <th className="px-3 py-2">Đăng nhập gần nhất</th>
              <th className="px-3 py-2">Trạng thái</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {(users.data ?? []).map((u) => (
              <UserRow key={u.id} user={u} isMe={u.username === me?.username} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
