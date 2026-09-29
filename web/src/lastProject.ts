// The project someone last opened, remembered so `/` and the sidebar land them back
// in it instead of the project picker every time.
export const LAST_PROJECT_KEY = 'vnstt.lastProject'

export function rememberProject(id: string) {
  try {
    localStorage.setItem(LAST_PROJECT_KEY, id)
  } catch {
    /* private mode: not remembered, still works */
  }
}

export function lastProjectId(): string | null {
  try {
    return localStorage.getItem(LAST_PROJECT_KEY)
  } catch {
    return null
  }
}
