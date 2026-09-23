import { useEffect, useState } from 'react'

import { Moon, Sun } from './Icons'

type Theme = 'light' | 'dark'
// Light is the default for everyone; only an explicit toggle is remembered. (The old
// 'vnstt.theme' key also stored the OS preference, so it can't tell choice from default.)
const KEY = 'vnstt.theme.choice'

function initial(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(initial)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  const setTheme = (t: Theme) => {
    setThemeState(t)
    try {
      localStorage.setItem(KEY, t)
    } catch {
      // private mode: the choice just isn't remembered
    }
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
