// Single shared password (PLAN §6 auth v1). One team, one password, one cookie.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '../api/client'

export default function Login() {
  const [password, setPassword] = useState('')
  const [editor, setEditor] = useState('')
  const queryClient = useQueryClient()

  const login = useMutation({
    mutationFn: () => api.login(password, editor || undefined),
    onSuccess: () => queryClient.invalidateQueries(),
  })

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-slate-200 bg-white p-6">
      <h1 className="text-lg font-semibold">VN-STT Corpus</h1>
      <p className="mt-1 text-sm text-slate-500">VOV2 · Đàn bà 30+</p>

      <form
        className="mt-5 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          login.mutate()
        }}
      >
        <label className="block text-sm">
          <span className="text-slate-600">Password</span>
          <input
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          />
        </label>

        <label className="block text-sm">
          <span className="text-slate-600">Your name (optional)</span>
          <input
            value={editor}
            onChange={(e) => setEditor(e.target.value)}
            placeholder="recorded against your edits"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
          />
        </label>

        <button
          type="submit"
          disabled={login.isPending || !password}
          className="w-full rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-40"
        >
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>

        {login.isError && (
          <p className="text-sm text-rose-600">
            {login.error instanceof ApiError ? login.error.detail : 'Sign-in failed'}
          </p>
        )}
      </form>
    </div>
  )
}
