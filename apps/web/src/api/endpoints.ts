import { api } from './client'
import type {
  Achievement,
  AdminStats,
  AgentJob,
  AgentTrace,
  LearningEvent,
  AskResponse,
  AssistantMode,
  AuthResponse,
  AuthUser,
  ChatMessage,
  ChatThread,
  Community,
  CompetitionResult,
  DocumentContent,
  DocumentRecord,
  GraphNodeDetail,
  GraphRebuildResult,
  GraphSearchResponse,
  GraphStatus,
  HealthResponse,
  InviteResult,
  Invitation,
  KnowledgeGapsResponse,
  KnowledgePack,
  LearnerSnapshot,
  OnboardingPath,
  Project,
  ProjectAnalytics,
  QuizAnswer,
  QuizAttempt,
  QuizInfo,
  QuizListEntry,
  QuizResult,
  RepositoryMap,
  ResumeItem,
  Role,
  RoleMatch,
  SearchResponse,
  SourceRecord,
  TeamMember,
} from './types'

const j = (body: unknown) => JSON.stringify(body)
export const changePassword = (body: { current_password: string; new_password: string }) => api<AuthResponse>('/api/auth/password', { method: 'POST', body: j(body) })
export const assignPath = (pathId: string, userId: string) => api<{ assigned: boolean }>(`/api/onboarding/path/${pathId}/members`, { method: 'POST', body: j({ user_id: userId }) })
export const rescoutPath = (pathId: string) => api<AgentJob>(`/api/onboarding/path/${pathId}/resource-scout`, { method: 'POST' })
export const getLeaderboardPreference = () => api<{ visible: boolean }>('/api/account/leaderboard-preference')
export const setLeaderboardPreference = (visible: boolean) => api<{ visible: boolean }>('/api/account/leaderboard-preference', { method: 'PATCH', body: j({ visible }) })
export const getLeaderboard = (projectId: string, pathId?: string) =>
  api<{ leaderboard: Array<{ user_id: string; display_name: string; xp: number; progress: number; streak: number; completed_items: number; passed_quizzes: number }> }>(`/api/projects/${projectId}/leaderboard${pathId ? '?path_id=' + encodeURIComponent(pathId) : ''}`)
export const getQuizHistory = (pathId: string, itemId: string, userId: string) =>
  api<Array<{ id: string; attempt_no: number; status: string; score: number | null; passed: boolean; questions: import('./types').QuizQuestion[]; answers: Record<string, QuizAnswer>; results: import('./types').QuizQuestionResult[]; hints: Record<string, Array<{ level: number; hint: string }>> }>>(`/api/onboarding/path/${pathId}/items/${itemId}/history?user_id=${encodeURIComponent(userId)}`)
export const getQuizHint = (attemptId: string, questionId: string, userId: string) =>
  api<{ level: number; hint: string }>(`/api/onboarding/quiz/attempts/${attemptId}/questions/${questionId}/hint`, { method: 'POST', body: j({ user_id: userId }) })

/* ---------- Auth ---------- */
export const register = (body: { email: string; password: string; display_name: string; role: 'manager' | 'learner'; role_title?: string }) =>
  api<AuthResponse>('/api/auth/register', { method: 'POST', body: j(body) })
export const login = (body: { email: string; password: string }) => api<AuthResponse>('/api/auth/login', { method: 'POST', body: j(body) })
export const acceptInviteWithPassword = (body: { token: string; display_name: string; password: string; email?: string | null }) =>
  api<AuthResponse>('/api/auth/accept-invite', { method: 'POST', body: j(body) })
export const getMe = () => api<AuthUser>('/api/auth/me')
/** Manager: give a person a workspace (and optionally a role profile). */
export const assignWorkspace = (projectId: string, body: { user_id: string; role_title?: string }) =>
  api<Array<{ user_id: string; role?: string }>>(`/api/projects/${projectId}/members`, { method: 'POST', body: j(body) })
export const unassignWorkspace = (projectId: string, userId: string) =>
  api<Array<{ user_id: string; role?: string }>>(`/api/projects/${projectId}/members/${userId}`, { method: 'DELETE' })
export const updateTeamMember = (userId: string, body: { role_title?: string; display_name?: string }) =>
  api<AuthUser>(`/api/team/${userId}`, { method: 'PATCH', body: j(body) })
export const updateMe = (body: { display_name?: string; role_title?: string }) => api<AuthUser>('/api/auth/me', { method: 'PATCH', body: j(body) })

/* ---------- System ---------- */
export const getHealth = () => api<HealthResponse>('/api/health')

/* ---------- Projects ---------- */
export const listProjects = (orgId: string) => api<Project[]>(`/api/projects?org_id=${encodeURIComponent(orgId)}`)
export const getProject = (projectId: string) => api<Project>(`/api/projects/${projectId}`)
export const createProject = (body: { org_id: string; user_id: string; name: string; description?: string }) =>
  api<Project>('/api/projects', { method: 'POST', body: j(body) })
export const getProjectMap = (projectId: string) => api<RepositoryMap>(`/api/projects/${projectId}/map`)

/* ---------- Team ---------- */
export const listTeam = (orgId: string) => api<TeamMember[]>(`/api/team?org_id=${encodeURIComponent(orgId)}`)
export const inviteTeammate = (body: { org_id: string; invited_by: string; email?: string | null; role_title?: string; project_id?: string | null }) =>
  api<InviteResult>('/api/team/invite', { method: 'POST', body: j(body) })
export const acceptInvite = (body: { token: string; display_name: string; email?: string | null; role_title?: string }) =>
  api<TeamMember>('/api/team/accept', { method: 'POST', body: j(body) })
export const listTeamInvitations = (orgId: string) => api<Invitation[]>(`/api/team/invites?org_id=${encodeURIComponent(orgId)}`)
export const revokeTeamInvitation = (orgId: string, token: string) =>
  api<{ ok: boolean }>(`/api/team/invites/${encodeURIComponent(token)}?org_id=${encodeURIComponent(orgId)}`, { method: 'DELETE' })
export const listMyInvitations = () => api<Invitation[]>('/api/invitations')
export const acceptExistingInvitation = (token: string) => api<AuthUser>(`/api/invitations/${encodeURIComponent(token)}/accept`, { method: 'POST', body: '{}' })


/* ---------- Sources ---------- */
export const listSources = (projectId: string) => api<SourceRecord[]>(`/api/projects/${projectId}/sources`)
export const listDocuments = (projectId: string) => api<DocumentRecord[]>(`/api/projects/${projectId}/documents`)
export const ingestSource = (body: {
  user_id: string
  project_id: string
  uri: string
  kind: 'auto' | 'github' | 'web' | 'gdrive'
  name?: string | null
  branch?: string | null
  access_token?: string | null
// Matches the backend's own git-clone timeout (600s) plus indexing headroom — the default 15s client
// timeout was aborting ingestion for any repository beyond a trivial one ("operation aborted").
}) => api<{ files?: number; [k: string]: unknown }>('/api/sources/ingest', { method: 'POST', body: j(body), timeoutMs: 600000 })
export const uploadSource = (projectId: string, file: File) => {
  const fd = new FormData()
  fd.append('project_id', projectId)
  fd.append('file', file)
  return api<{ files?: number; [k: string]: unknown }>('/api/sources/upload', { method: 'POST', body: fd, timeoutMs: 120000 })
}

/* ---------- Search ---------- */
export const hybridSearch = (body: { project_id: string; query: string; top_k?: number; filters?: Record<string, unknown> }) =>
  api<SearchResponse>('/api/search', { method: 'POST', body: j(body) })

/* ---------- Assistant ---------- */
export const askAssistant = (body: {
  user_id: string
  project_id: string
  question: string
  thread_id?: string | null
  mode?: AssistantMode
  current_code?: string | null
  file_path?: string | null
  hint_level?: number
  allow_final_answer?: boolean
  // A 1500-token QA answer at the model's current serving throughput (~9-10 tok/s measured) plus
  // retrieval overhead genuinely takes 2-4+ minutes end to end — 120s was aborting successful requests.
}) => api<AskResponse>('/api/ask', { method: 'POST', body: j(body), timeoutMs: 300000 })

export const listChatThreads = (userId: string, projectId?: string) =>
  api<ChatThread[]>(`/api/chats/${userId}${projectId ? `?project_id=${projectId}` : ''}`)
export const getThreadMessages = (threadId: string) => api<ChatMessage[]>(`/api/chats/thread/${threadId}`)

export const startResearch = (body: { user_id: string; project_id: string; query: string; depth?: 'quick' | 'standard' | 'deep' }) =>
  api<AgentJob>('/api/research', { method: 'POST', body: j(body) })

/* ---------- Onboarding / Learning ---------- */
export const createOnboarding = (body: {
  user_id: string
  project_id: string
  target_role: string
  level: 'junior' | 'mid' | 'senior'
  weeks: number
  hours_per_week: number
  background?: string
  is_public?: boolean
  /** Graph-grounded roadmap ('graph') or LLM-only ('llm'). Server default: graph when a graph exists. */
  engine?: 'graph' | 'llm'
  role_id?: string
  /** 4-8 questions per section quiz. */
  quiz_questions?: number
  scope?: string
}) => api<OnboardingPath>('/api/onboarding', { method: 'POST', body: j(body), timeoutMs: 120000 })

export const listPaths = (projectId: string, userId: string) => api<OnboardingPath[]>(`/api/onboarding/${projectId}?user_id=${userId}`)
export const getPath = (pathId: string, userId: string) => api<OnboardingPath>(`/api/onboarding/path/${pathId}?user_id=${userId}`)
export const joinPath = (pathId: string, body: { user_id: string; invite_code?: string | null }) =>
  api<OnboardingPath>(`/api/onboarding/path/${pathId}/join`, { method: 'POST', body: j(body) })
export const updateProgress = (
  pathId: string,
  body: { user_id: string; item_id: string; status: 'not_started' | 'in_progress' | 'completed'; progress: number; score?: number | null }
) => api<{ xp_delta?: number; xp?: number; overall?: number; streak?: number; [k: string]: unknown }>(
  `/api/onboarding/path/${pathId}/progress`,
  { method: 'POST', body: j(body) }
)

/* ---------- Resources / resume ---------- */
export const upsertResourceSession = (body: {
  user_id: string
  project_id?: string
  url: string
  title?: string
  resource_type?: string
  seconds_active?: number
  progress?: number
  last_position?: number
  duration?: number | null
  visible_text?: string | null
  concepts?: string[]
}) => api<Record<string, unknown>>('/api/resource/session', { method: 'POST', body: j(body) })

export const getResumeFeed = (userId: string, projectId?: string) =>
  api<ResumeItem[]>(`/api/resource/resume/${userId}${projectId ? `?project_id=${projectId}` : ''}`)

/* ---------- Events ---------- */
export const sendEvent = (body: {
  event_id?: string
  user_id: string
  project_id?: string
  source?: 'browser' | 'vscode' | 'webapp' | 'research' | 'system'
  type: string
  resource_id?: string
  context?: Record<string, unknown>
}) => api<Record<string, unknown>>('/api/events', { method: 'POST', body: j({ source: 'webapp', ...body }) })

export const getEvents = (userId: string, projectId?: string, limit = 50) =>
  api<LearningEvent[]>(`/api/events/${userId}?${projectId ? `project_id=${projectId}&` : ''}limit=${limit}`)

/* ---------- Learner / mastery ---------- */
export const getLearnerSnapshot = (userId: string, projectId: string) => api<LearnerSnapshot>(`/api/learner/${userId}/${projectId}`)

/* ---------- Admin / engineering ---------- */
export const getAdminStats = (orgId: string) => api<AdminStats>(`/api/admin/stats?org_id=${encodeURIComponent(orgId)}`)
export const getTraces = (limit = 100) => api<AgentTrace[]>(`/api/admin/traces?limit=${limit}`)
export const getCompetition = () => api<CompetitionResult>('/api/admin/competition')

/* ---------- Agent jobs ---------- */
export const getAgentJob = (jobId: string) => api<AgentJob>(`/api/agent/jobs/${jobId}`)

/* ---------- Roles ---------- */
export const listRoleProfiles = () => api<{ roles: Role[] }>('/api/role-profiles')
export const matchRole = (title: string) => api<RoleMatch>(`/api/roles/match?title=${encodeURIComponent(title)}`)

/* ---------- Knowledge graph ---------- */
export const getGraphStatus = (projectId: string) => api<GraphStatus>(`/api/projects/${projectId}/graph/status`)
/** Synchronous rebuild; can take a while on large repositories. */
export const rebuildGraph = (projectId: string) =>
  api<GraphRebuildResult>(`/api/projects/${projectId}/graph/rebuild`, { method: 'POST', body: '{}', timeoutMs: 300000 })
export const listCommunities = (projectId: string) => api<Community[]>(`/api/projects/${projectId}/graph/communities`)
export const getGraphNode = (projectId: string, nodeId: string) =>
  api<GraphNodeDetail>(`/api/projects/${projectId}/graph/node/${encodeURIComponent(nodeId)}`)
export const graphSearch = (body: { project_id: string; query: string; role?: string; top_k?: number }) =>
  api<GraphSearchResponse>('/api/graph/search', { method: 'POST', body: j(body) })

/* ---------- Knowledge pack ---------- */
export const getKnowledgePack = (projectId: string, params: { role?: string; scope?: string; limit?: number } = {}) => {
  const q = new URLSearchParams()
  if (params.role) q.set('role', params.role)
  if (params.scope) q.set('scope', params.scope)
  if (params.limit) q.set('limit', String(params.limit))
  const qs = q.toString()
  return api<KnowledgePack>(`/api/projects/${projectId}/knowledge-pack${qs ? `?${qs}` : ''}`, { timeoutMs: 60000 })
}
export const getDocumentContent = (documentId: string, range: { start_line?: number | null; end_line?: number | null } = {}) => {
  const q = new URLSearchParams()
  if (range.start_line != null) q.set('start_line', String(range.start_line))
  if (range.end_line != null) q.set('end_line', String(range.end_line))
  const qs = q.toString()
  return api<DocumentContent>(`/api/documents/${encodeURIComponent(documentId)}/content${qs ? `?${qs}` : ''}`)
}

/* ---------- Role onboarding ---------- */
export const startRoleOnboarding = (body: { user_id: string; project_id: string; role?: string; level?: 'junior' | 'mid' | 'senior' }) =>
  api<OnboardingPath>('/api/onboarding/for-role', { method: 'POST', body: j(body), timeoutMs: 120000 })

/* ---------- Quizzes ---------- */
const quizBase = (pathId: string, itemId: string) => `/api/onboarding/path/${pathId}/items/${encodeURIComponent(itemId)}/quiz`
export const getQuiz = (pathId: string, itemId: string, userId: string) => api<QuizInfo>(`${quizBase(pathId, itemId)}?user_id=${encodeURIComponent(userId)}`)
export const startQuiz = (pathId: string, itemId: string, userId: string) =>
  api<QuizAttempt>(`${quizBase(pathId, itemId)}/start`, { method: 'POST', body: j({ user_id: userId }), timeoutMs: 60000 })
export const submitQuiz = (attemptId: string, body: { user_id: string; answers: Record<string, QuizAnswer> }) =>
  api<QuizResult>(`/api/onboarding/quiz/attempts/${attemptId}/submit`, { method: 'POST', body: j(body), timeoutMs: 90000 })
export const listQuizzes = (pathId: string, userId: string) => api<QuizListEntry[]>(`/api/onboarding/path/${pathId}/quizzes?user_id=${encodeURIComponent(userId)}`)

/* ---------- Achievements and analytics ---------- */
export const getUserAchievements = (userId: string, projectId?: string) =>
  api<Achievement[]>(`/api/users/${userId}/achievements${projectId ? `?project_id=${projectId}` : ''}`)
export const getProjectAchievements = (projectId: string) => api<Achievement[]>(`/api/projects/${projectId}/achievements`)
export const getKnowledgeGaps = (projectId: string) => api<KnowledgeGapsResponse>(`/api/projects/${projectId}/knowledge-gaps`)
export const getProjectAnalytics = (projectId: string) => api<ProjectAnalytics>(`/api/projects/${projectId}/analytics`)
