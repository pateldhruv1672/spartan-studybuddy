export interface NavItem {
  to: string
  label: string
  icon: string
  roles: Array<'manager' | 'learner'>
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/manager', label: 'Overview', icon: '⌂', roles: ['manager'] },
  { to: '/learn', label: 'Home', icon: '⌂', roles: ['learner'] },
  { to: '/sources', label: 'Knowledge', icon: '◫', roles: ['manager'] },
  { to: '/architecture', label: 'Architecture', icon: '▦', roles: ['manager', 'learner'] },
  { to: '/repository', label: 'Repository', icon: '◈', roles: ['manager', 'learner'] },
  { to: '/paths', label: 'Paths', icon: '↗', roles: ['manager', 'learner'] },
  { to: '/kit', label: 'Onboarding kit', icon: '❖', roles: ['manager', 'learner'] },
  { to: '/assistant', label: 'StudyBuddy', icon: '✦', roles: ['manager', 'learner'] },
  { to: '/progress', label: 'My progress', icon: '★', roles: ['learner'] },
  { to: '/team', label: 'Team', icon: '◎', roles: ['manager'] },
  { to: '/leaderboard', label: 'Leaderboard', icon: '♜', roles: ['manager', 'learner'] },
  { to: '/analytics', label: 'Analytics', icon: '▤', roles: ['manager'] },
  { to: '/engineering', label: 'Engineering', icon: '⌁', roles: ['manager'] },
]
