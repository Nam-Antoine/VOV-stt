// The signed-in account, shared by every page through the ['session'] query that
// App.tsx uses as its route guard.
import { useQuery } from '@tanstack/react-query'

import { api } from './client'

export function useMe() {
  return useQuery({ queryKey: ['session'], queryFn: () => api.me(), retry: false }).data
}

export function useIsAdmin() {
  return useMe()?.role === 'admin'
}
