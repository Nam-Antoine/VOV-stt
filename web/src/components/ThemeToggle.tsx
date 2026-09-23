import { useSyncExternalStore } from 'react'

import { Moon, Sun } from './Icons'

type Theme = 'light' | 'dark'
// Light is the default for everyone; only an explicit toggle is remembered. (The old
// 'vnstt.theme' key also stored the OS preference, so it can't tell choice from default.)
const KEY = 'vnstt.theme.choice'

// The <html> class is the one source of truth: the boot script in index.html sets it
// before first paint, and every toggle on the page (the sidebar's and the phone
// header's are both mounted) reads it through this store, so they never disagree.
const listeners = new Set<() => void>()
const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => void listeners.delete(cb)
}
const current = (): Theme => (document.documentElement.classList.contains('dark') ? 'dark' : 'light')

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current)

  const setTheme = (t: Theme) => {
    document.documentElement.classList.toggle('dark', t === 'dark')
    try {
      localStorage.setItem(KEY, t)
    } catch {
      // private mode: the choice just isn't remembered
    }
    listeners.forEach((cb) => cb())
  }

  return { theme, setTheme }
}

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = next === 'dark' ? 'Chuyển sang giao diện tối' : 'Chuyển sang giao diện sáng'
  return (
    <button
      onClick={() => setTheme(next)}
      className="btn-ghost btn-sm"
      title={label}
      aria-label={label}
    >
      {theme === 'dark' ? <Sun /> : <Moon />}
    </button>
  )
}
