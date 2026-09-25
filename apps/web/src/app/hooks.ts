import { useQueries, useQuery } from '@tanstack/react-query'
import { getPath, listPaths } from '../api/endpoints'
import type { OnboardingPath, PathMember } from '../api/types'
import { useSessionStore } from './sessionStore'

/** Paths visible to the current user in the active workspace, each with full member/progress detail. */
export function usePathDetails() {
  const { userId, projectId } = useSessionStore()
  const list = useQuery({ queryKey: ['paths', projectId, userId], queryFn: () => listPaths(projectId!, userId), enabled: !!projectId && !!userId })
  const details = useQueries({
    queries: (list.data || []).map((p) => ({
      queryKey: ['path', p.id, userId],
      queryFn: () => getPath(p.id, userId),
    })),
  })
  const paths = details.map((d) => d.data).filter(Boolean) as OnboardingPath[]
  const loading = list.isLoading || details.some((d) => d.isLoading)
  return { list, paths, loading }
}

export interface Membership extends PathMember {
  path: OnboardingPath
}

export function myMemberships(paths: OnboardingPath[], userId: string): Membership[] {
  return paths.flatMap((path) => (path.members || []).filter((m) => m.user_id === userId).map((m) => ({ ...m, path })))
}

export function pct(value?: number | null) {
  return `${Math.round((value || 0) * 100)}%`
}
