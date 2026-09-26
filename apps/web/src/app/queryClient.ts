import { QueryClient } from '@tanstack/react-query'
import { isAppError } from '../api/client'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (isAppError(error) && !error.retryable) return false
        return failureCount < 2
      },
      staleTime: 15000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
})
