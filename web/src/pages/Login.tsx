// Per-user login. Accounts are created by an admin; there is no sign-up.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import { Spinner } from '../components/Icons'
import ThemeToggle from '../components/ThemeToggle'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const queryClient = useQueryClient()

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: (me) => {
      queryClient.setQueryData(['session'], me)
      queryClient.invalidateQueries()
    },
    onError: () => setPassword(''),
  })

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-6 text-center">
          <img src="/favicon.svg" alt="" width={48} height={48} className="mx-auto h-12 w-12" />
          <h1 className="title mt-3">Kho ngữ liệu VN-STT</h1>
          <p className="mt-1 text-sm text-muted">VOV2 · Đàn bà 30+</p>
        </div>

        <form
          className="card space-y-3 p-6"
          onSubmit={(e) => {
            e.preventDefault()
            login.mutate()
          }}
        >
          <label className="block text-sm">
            <span className="text-muted">Tên đăng nhập</span>
            <input
              name="username"
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="field mt-1"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted">Mật khẩu</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field mt-1"
            />
          </label>

          <button
            type="submit"
            disabled={login.isPending || !username.trim() || !password}
            className="btn-primary w-full"
          >
            {login.isPending ? <Spinner className="h-4 w-4" /> : null}
            {login.isPending ? 'Đang đăng nhập…' : 'Đăng nhập'}
          </button>

          {login.isError && (
            <p className="text-sm text-rose-600 dark:text-rose-400" role="alert">
              {login.error instanceof ApiError ? login.error.detail : 'Đăng nhập thất bại'}
            </p>
          )}
        </form>

        <p className="mt-4 text-center text-xs leading-relaxed text-faint">
          Chưa có tài khoản hoặc quên mật khẩu? Liên hệ quản trị viên.
        </p>
      </div>
    </div>
  )
}
