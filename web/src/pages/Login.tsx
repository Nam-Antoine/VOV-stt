// Single shared password (PLAN §6 auth v1). One team, one password, one cookie.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'
import { Spinner } from '../components/Icons'
import ThemeToggle from '../components/ThemeToggle'

export default function Login() {
  const [password, setPassword] = useState('')
  const [editor, setEditor] = useState('')
  const queryClient = useQueryClient()

  const login = useMutation({
    mutationFn: () => api.login(password, editor || undefined),
    onSuccess: () => queryClient.invalidateQueries(),
  })

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold">VN-STT Corpus</h1>
          <p className="mt-0.5 text-sm text-muted">VOV2 · Đàn bà 30+</p>
        </div>

        <form
          className="card space-y-3 p-6"
          onSubmit={(e) => {
            e.preventDefault()
            login.mutate()
          }}
        >
          <label className="block text-sm">
            <span className="text-muted">Password</span>
            <input
              type="password"
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field mt-1"
            />
          </label>

          <label className="block text-sm">
            <span className="text-muted">Your name</span>
            <input
              value={editor}
              onChange={(e) => setEditor(e.target.value)}
              placeholder="optional — recorded against your edits"
              className="field mt-1"
            />
          </label>

          <button
            type="submit"
            disabled={login.isPending || !password}
            className="btn-primary w-full"
          >
            {login.isPending ? <Spinner className="h-4 w-4" /> : null}
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </button>

          {login.isError && (
            <p className="text-sm text-rose-600 dark:text-rose-400" role="alert">
              {login.error instanceof ApiError ? login.error.detail : 'Sign-in failed'}
            </p>
          )}
        </form>

        <p className="mt-4 text-center text-xs leading-relaxed text-faint">
          A verbatim linguistic corpus. Fillers, repetitions and false starts are the
          data, not mistakes.
        </p>
      </div>
    </div>
  )
}
