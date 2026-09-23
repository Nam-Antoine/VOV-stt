// Your own account: who you are and changing your password.
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import { useMe } from '../api/session'

export default function Account() {
  const me = useMe()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')

  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setCurrent('')
      setNext('')
      setAgain('')
    },
  })

  const mismatch = again.length > 0 && next !== again

  return (
    <section className="max-w-md">
      <header className="mb-6">
        <p className="eyebrow">{me?.role === 'admin' ? 'Quản trị viên' : 'Biên tập viên'}</p>
        <h1 className="title mt-1">{me?.display_name || me?.username}</h1>
        <p className="mt-1.5 text-sm text-muted">
          Tên đăng nhập: <b className="font-semibold text-ink">{me?.username}</b>. Các chỉnh sửa
          của bạn được ghi lại dưới tên này.
        </p>
      </header>

      <form
        className="card space-y-3 p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (!mismatch) change.mutate()
        }}
      >
        <h2 className="font-semibold">Đổi mật khẩu</h2>
        {/* Hidden username so password managers file the new password under the right account. */}
        <input type="text" autoComplete="username" value={me?.username ?? ''} readOnly hidden />
        <label className="block text-sm">
          <span className="text-muted">Mật khẩu hiện tại</span>
          <input type="password" autoComplete="current-password" value={current}
            onChange={(e) => setCurrent(e.target.value)} className="field mt-1" />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Mật khẩu mới (ít nhất 10 ký tự)</span>
          <input type="password" autoComplete="new-password" minLength={10} value={next}
            onChange={(e) => setNext(e.target.value)} className="field mt-1" />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Nhập lại mật khẩu mới</span>
          <input type="password" autoComplete="new-password" value={again}
            onChange={(e) => setAgain(e.target.value)} className="field mt-1" />
        </label>
        {mismatch && <p className="text-sm text-rose-600 dark:text-rose-400">Mật khẩu nhập lại không khớp.</p>}
        <button type="submit" disabled={!current || next.length < 10 || next !== again || change.isPending}
          className="btn-primary w-full">
          {change.isPending ? 'Đang lưu…' : 'Đổi mật khẩu'}
        </button>
        {change.isSuccess && (
          <p className="text-sm text-ink">Đã đổi mật khẩu. Các thiết bị khác đã bị đăng xuất.</p>
        )}
        {change.isError && (
          <p className="text-sm text-rose-600 dark:text-rose-400" role="alert">
            {change.error instanceof ApiError ? change.error.detail : 'Thất bại'}
          </p>
        )}
      </form>
    </section>
  )
}
