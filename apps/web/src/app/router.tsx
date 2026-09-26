import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/navigation/AppShell'
import { RequireAuth } from '../components/navigation/RequireAuth'
import { useSessionStore } from './sessionStore'
import { LoginPage } from '../pages/LoginPage'
import { JoinPage } from '../pages/JoinPage'
import { WorkspacePage } from '../pages/WorkspacePage'
import { ManagerDashboardPage } from '../pages/ManagerDashboardPage'
import { SourcesPage } from '../pages/SourcesPage'
import { RepositoryMapPage } from '../pages/RepositoryMapPage'
import { PathsPage } from '../pages/PathsPage'
import { KnowledgePackPage } from '../pages/KnowledgePackPage'
import { PathBuilderPage } from '../pages/PathBuilderPage'
import { PathDetailPage } from '../pages/PathDetailPage'
import { LearnerDashboardPage } from '../pages/LearnerDashboardPage'
import { StudyPage } from '../pages/StudyPage'
import { AssistantPage } from '../pages/AssistantPage'
import { LeaderboardPage } from '../pages/LeaderboardPage'
import { AnalyticsPage } from '../pages/AnalyticsPage'
import { EngineeringLabPage } from '../pages/EngineeringLabPage'
import { ArchitecturePage } from '../pages/ArchitecturePage'
import { TeamPage } from '../pages/TeamPage'
import { ProgressPage } from '../pages/ProgressPage'
import { IntegrationsPage } from '../pages/IntegrationsPage'
import { SettingsPage } from '../pages/SettingsPage'
import { NotFoundPage } from '../pages/NotFoundPage'

function ManagerOnly() {
  const role = useSessionStore((s) => s.role)
  return role === 'manager' ? <Outlet /> : <Navigate to="/learn" replace />
}

function RoleHome() {
  const role = useSessionStore((s) => s.role)
  return <Navigate to={role === 'manager' ? '/manager' : '/learn'} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/join/:token" element={<JoinPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route element={<AppShell />}>
          <Route element={<ManagerOnly />}>
            <Route path="/manager" element={<ManagerDashboardPage />} />
            <Route path="/sources" element={<SourcesPage />} />
            <Route path="/paths/new" element={<PathBuilderPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/engineering" element={<EngineeringLabPage />} />
            <Route path="/team" element={<TeamPage />} />
          </Route>
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/integrations" element={<IntegrationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/architecture" element={<ArchitecturePage />} />
          <Route path="/repository" element={<RepositoryMapPage />} />
          <Route path="/kit" element={<KnowledgePackPage />} />
          <Route path="/paths" element={<PathsPage />} />
          <Route path="/paths/:pathId" element={<PathDetailPage />} />
          <Route path="/learn" element={<LearnerDashboardPage />} />
          <Route path="/study/:pathId/:itemId?" element={<StudyPage />} />
          <Route path="/assistant/:threadId?" element={<AssistantPage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/" element={<RoleHome />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
