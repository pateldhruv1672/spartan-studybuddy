export interface HealthResponse {
  ok: boolean
  name: string
  database: Record<string, unknown>
  model_endpoints: Record<string, boolean>
}

export interface Project {
  id: string
  org_id: string
  name: string
  description: string
  created_at?: string
  members?: ProjectMember[]
  [key: string]: unknown
}

export interface ProjectMember {
  user_id: string
  display_name?: string
  role_title?: string
  [key: string]: unknown
}

export interface MapFile {
  source_name: string
  source_type: string
  language: string | null
}

export interface MapSymbol {
  name: string
  kind: string
  language: string | null
  start_line: number | null
  end_line: number | null
  document_id: string
}

export interface MapEdge {
  source_symbol: string
  target_symbol: string
  edge_type: string
}

export interface RepositoryMap {
  documents: number
  files: MapFile[]
  languages: Record<string, number>
  symbols: MapSymbol[]
  edges: MapEdge[]
}

export interface SourceRecord {
  id: string
  project_id: string
  kind: 'github' | 'web' | 'gdrive' | 'upload' | 'auto' | string
  name: string
  uri?: string
  status: string
  created_at?: string
  [key: string]: unknown
}

export interface DocumentRecord {
  id: string
  source_id?: string | null
  source_type: string
  source_name: string
  source_uri?: string | null
  mime_type?: string | null
  language?: string | null
  indexed_at?: string
  metadata?: Record<string, unknown>
}

export interface SearchHit {
  source_name: string
  content: string
  citation?: string
  score?: number
  [key: string]: unknown
}

export interface SearchResponse {
  results: SearchHit[]
}

export type AssistantMode = 'auto' | 'qa' | 'socratic' | 'explain' | 'code' | 'research'

export interface AskResponse {
  thread_id: string
  mode: AssistantMode | 'research'
  answer: string
  sources?: Array<{ ref?: string; citation?: string; source_name?: string; [key: string]: unknown }>
  metrics?: { ttft_ms?: number; tokens_per_second?: number; [key: string]: unknown }
  job_id?: string
  [key: string]: unknown
}

export interface ChatThread {
  id: string
  title?: string
  mode?: string
  updated_at?: string
  [key: string]: unknown
}

export interface ChatMessage {
  job_id?: string
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: AskResponse['sources']
  metrics?: AskResponse['metrics']
  created_at?: string
  [key: string]: unknown
}

/** A grounded reference to a graph node (file, doc section, symbol) with why it matters. */
export interface NodeRef {
  node_id: string
  kind: GNodeKind | string
  name: string
  path?: string
  start_line?: number | null
  end_line?: number | null
  reasons?: string[]
  citation?: string
  /** Not in the v1 contract, but tolerated so the drawer can open a document directly when present. */
  document_id?: string | null
}

export type PlanItemType =
  | 'internal_walkthrough'
  | 'doc_reading'
  | 'concept'
  | 'external_resource'
  | 'checkpoint'
  | 'quiz'
  | 'exercise'

export interface PathModuleItem {
  id: string
  title: string
  type?: PlanItemType | string
  minutes?: number
  xp?: number
  repo_refs?: string[]
  node_refs?: NodeRef[]
  topic?: string
  checkpoint_question?: string
  quiz?: { question_count: number; pass_threshold: number }
  [key: string]: unknown
}

export type ModuleKind = 'foundations' | 'orientation' | 'subsystem' | 'handson' | 'capstone'

export interface PathModule {
  id?: string
  title: string
  outcome?: string
  kind?: ModuleKind | string
  objectives?: string[]
  community_id?: string
  concept_ids?: string[]
  minutes?: number
  items: PathModuleItem[]
}

export interface PathExercise {
  id: string
  title: string
  difficulty?: string
  description?: string
  repo_refs?: string[]
  acceptance?: string[]
  xp?: number
}

export interface PlanMeta {
  engine: 'graph' | 'llm'
  role_profile_id?: string
  role_title?: string
  graph_build_id?: string
  quiz_pass_threshold?: number
  gating?: boolean
  generated_at?: string
  budget_minutes?: number
  estimated_minutes?: number
  dropped_sections?: string[]
  provenance?: 'graph' | 'generated' | 'fallback'
  requires_review?: boolean
  warning?: string
  warnings?: string[]
  coverage?: { sections: number; sections_with_evidence: number; top_files: number; top_files_covered: number; ratio: number | null }
}

export interface PathPlan {
  summary?: string
  meta?: PlanMeta
  prerequisites?: Array<{ concept: string; concept_id?: string; priority?: string; reason?: string }>
  modules: PathModule[]
  exercises?: PathExercise[]
  resource_search_topics?: string[]
}

export interface PathMember {
  user_id: string
  display_name?: string | null
  role_title?: string | null
  avatar?: string | null
  xp?: number
  progress?: number
  streak?: number
  joined_at?: string
}

export interface OnboardingPath {
  id: string
  project_id: string
  target_role: string
  level: 'junior' | 'mid' | 'senior'
  weeks: number
  hours_per_week: number
  is_public: boolean
  invite_code?: string
  plan: PathPlan
  members?: PathMember[]
  creator_id?: string
  title?: string
  created_at?: string
  progress_items?: Array<{ item_id: string; status: string; progress: number }>
  resources?: Array<{ title: string; url: string; resource_type?: string; source?: string; rationale?: string; topic?: string; metadata?: { screenshot_base64?: string; [key: string]: unknown } }>
  resource_job?: AgentJob | null
  /** Graph-grounded paths: per quiz item state, and every item locked behind an unpassed quiz. */
  quiz_status?: Record<string, QuizStatus>
  locked_items?: string[]
  [key: string]: unknown
}

export interface ResumeItem {
  id?: string
  resource_type?: string
  resource_title?: string
  resource_url: string
  progress?: number
  summary?: string | null
  seconds_active?: number
  last_position?: number
  duration?: number | null
  concepts?: string[]
  questions?: Array<string | { question?: string; [key: string]: unknown }>
  last_seen_at?: string
  [key: string]: unknown
}

export interface LearningEvent {
  id: string
  type: string
  source: string
  resource_id?: string | null
  context?: Record<string, unknown>
  created_at: string
}

export interface MemoryItem {
  id: string
  kind: string
  title: string
  content: string
  importance: number
  created_at: string
  [key: string]: unknown
}

export interface MasteryRow {
  topic: string
  score: number
  confidence?: number
  updated_at?: string
}

export interface LearnerSnapshot {
  mastery?: MasteryRow[]
  memories?: MemoryItem[]
  recent_events?: LearningEvent[]
  [key: string]: unknown
}

export interface AgentJob {
  id: string
  kind: string
  status: string
  payload?: Record<string, unknown>
  result?: { synthesis?: string; resources?: Array<{ title?: string; url?: string; summary?: string }>; [key: string]: unknown } | null
  created_at?: string
  updated_at?: string
}

export interface AdminStats {
  users?: number
  projects?: number
  documents?: number
  onboarding_paths?: number
  agent_traces?: number
  leaderboard?: Array<{ user_id?: string; display_name?: string | null; xp?: number | null; progress?: number | null }>
  [key: string]: unknown
}

export interface AgentTrace {
  id?: string
  agent: string
  user_id?: string | null
  project_id?: string | null
  route?: string | null
  model?: string | null
  prompt_preview?: string
  response_preview?: string
  retrieved?: Array<{ citation?: string; source?: string }>
  latency_ms?: number | null
  ttft_ms?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  tokens_per_second?: number | null
  success?: number | boolean
  metadata?: Record<string, unknown>
  created_at?: string
}

/** Mirrors experiments/compare_results.py output. */
export interface CompetitionSummary {
  socratic_quality?: {
    base_score?: number
    tuned_score?: number
    score_delta_points?: number
    base_answer_leak_rate?: number
    tuned_answer_leak_rate?: number
    answer_leak_reduction_pct?: number
    base_question_rate?: number
    tuned_question_rate?: number
    base_guidance_marker_rate?: number
    tuned_guidance_marker_rate?: number
    base_concise_rate?: number
    tuned_concise_rate?: number
  }
  serving_base_vs_tuned?: {
    base_ttft_p50_s?: number
    tuned_ttft_p50_s?: number
    base_decode_tok_s_p50?: number
    tuned_decode_tok_s_p50?: number
    base_aggregate_tok_s?: number
    tuned_aggregate_tok_s?: number
  }
  speculative_decoding?: {
    baseline_profile?: string
    spec_profile?: string
    ttft_change_pct?: number | null
    decode_tok_s_change_pct?: number | null
    aggregate_tok_s_change_pct?: number | null
    baseline_decode_tok_s_p50?: number
    spec_decode_tok_s_p50?: number
    baseline_ttft_p50_s?: number
    spec_ttft_p50_s?: number
  }
}

export interface CompetitionResult extends CompetitionSummary {
  available?: boolean
  message?: string
  summary?: CompetitionSummary
}

export interface ServingProfile {
  method: string
  label: string
  artifact?: string | null
  profile?: string | null
  model?: string | null
  requests?: number | null
  concurrency?: number | null
  ttft_p50_s?: number | null
  ttft_p95_s?: number | null
  decode_tok_s_p50?: number | null
  aggregate_output_tok_s?: number | null
  draft_acceptance_rate?: number | null
  mean_acceptance_length?: number | null
  recommended: boolean
}

export interface TrafficSummary {
  generated_at: string
  sample_size: number
  success_rate?: number | null
  latency_p50_ms?: number | null
  latency_p95_ms?: number | null
  ttft_p50_ms?: number | null
  tokens_in: number
  tokens_out: number
  routes: string[]
}

export interface ServingProfileResult {
  available: boolean
  selected_method?: string | null
  profiles: ServingProfile[]
  message?: string
}

export interface TeamMember {
  id: string
  display_name: string
  workspace_ids?: string[]
  app_role?: 'manager' | 'learner'
  email?: string
  role_title?: string
  avatar?: string
  [key: string]: unknown
}

export interface AuthUser {
  id: string
  org_id: string
  display_name: string
  email: string
  role_title?: string
  avatar?: string
  role: 'manager' | 'learner'
}

export interface AuthResponse {
  token: string
  user: AuthUser
}

export interface InviteResult {
  token: string
  join_url?: string
  [key: string]: unknown
}

export interface Invitation {
  id: string
  token: string
  org_id: string
  organization_name: string
  email: string
  role_title?: string
  project_id?: string | null
  project_name?: string | null
  status: 'pending' | 'accepting' | 'accepted' | 'revoked'
  created_at: string
  expires_at?: string | null
  accepted_at?: string | null
  expired: boolean
  join_url: string
}

/* ---------- Roles ---------- */
export interface RoleConcept {
  id: string
  name: string
  weight: number
}

export interface Role {
  id: string
  title: string
  description: string
  aliases: string[]
  first_contribution: string
  concepts: RoleConcept[]
}

export interface RoleMatch {
  role_id: string
  title: string
  /** 0..1; 0 means it fell back to software-engineer. */
  confidence: number
}

/* ---------- Knowledge graph ---------- */
export type GNodeKind = 'repo' | 'dir' | 'file' | 'doc' | 'section' | 'symbol' | 'tech' | 'concept' | 'link'

export interface GNode {
  id: string
  kind: GNodeKind
  name: string
  path?: string | null
  document_id?: string | null
  start_line?: number | null
  end_line?: number | null
  language?: string | null
  summary?: string | null
  community_id?: string | null
  meta: Record<string, unknown>
}

export interface Community {
  id: string
  name: string
  summary: string
  size: number
  keywords: string[]
  summary_source: 'template' | 'llm'
  meta: Record<string, unknown>
}

export interface GraphBuildInfo {
  id: string
  status: string
  stats?: Record<string, unknown> | null
  finished_at?: string | null
}

export interface GraphStatus {
  ready: boolean
  stale: boolean
  building: boolean
  documents: number
  build: GraphBuildInfo | null
}

export interface GraphRebuildResult {
  build_id: string
  status: string
  nodes: number
  edges: number
  communities: number
  import_resolution_rate: number
  mention_link_rate: number
  node_kinds: Record<string, number>
  edge_types: Record<string, number>
  seconds: number
}

export interface GraphNeighbor {
  node: GNode
  type: string
  weight: number
  direction: 'out' | 'in'
}

export interface GraphNodeDetail {
  node: GNode
  community: Community | null
  neighbors: GraphNeighbor[]
}

export interface GraphSearchHit extends SearchHit {
  via?: Array<{ type: string; from: string }>
}

export interface GraphSearchResponse {
  results: GraphSearchHit[]
  structure: string[]
  communities: Community[]
}

/* ---------- Knowledge pack ---------- */
export interface PackItem {
  node_id: string
  kind: GNodeKind | string
  name: string
  path: string
  language?: string | null
  document_id?: string | null
  start_line?: number | null
  end_line?: number | null
  /** 0..1 */
  relevance: number
  /** Why this matters for the chosen role. */
  reasons: string[]
  /** "path:12-40" */
  citation: string
}

export interface PackSubsystem {
  community: { id: string; name: string; summary: string; size: number }
  relevance: number
  items: PackItem[]
  depends_on: string[]
  used_by: string[]
}

export interface PackLink {
  url: string
  title: string
  host: string
  found_in: string[]
}

export interface PackTechnology {
  id: string
  name: string
  category: string
  public: boolean
  files: number
}

export interface PackConcept {
  id: string
  name: string
  area: string
  weight: number
  why: string
  prereqs: string[]
}

export interface PackGlossaryEntry {
  term: string
  definition: string
  /** Citation string for the source of the definition. */
  source: string
}

export interface SubgraphNode {
  id: string
  kind: GNodeKind | string
  name: string
  path?: string | null
  relevance: number
}

export interface SubgraphEdge {
  src: string
  dst: string
  type: string
  weight: number
}

export interface KnowledgePack {
  role: { id: string; title: string; description: string; confidence: number }
  build_id: string
  generated_at: string
  start_here: PackItem[]
  core_modules: PackItem[]
  subsystems: PackSubsystem[]
  docs: PackItem[]
  external_links: PackLink[]
  technologies: PackTechnology[]
  concepts: PackConcept[]
  glossary: PackGlossaryEntry[]
  subgraph: { nodes: SubgraphNode[]; edges: SubgraphEdge[] }
  signals: { dense: boolean; seeds: number; seed_kinds: Record<string, number> }
  stats: { files_ranked: number; docs_ranked: number }
}

export interface DocumentContent {
  document_id: string
  path: string
  language?: string | null
  start_line: number
  end_line: number
  content: string
  truncated: boolean
  // Canonical external URL (GitHub blob, the original web page, ...) when the source has one — never
  // guessed client-side. Null for uploads/local sources that have no public location.
  external_url: string | null
}

/* ---------- Quizzes ---------- */
export interface QuizStatus {
  passed: boolean
  best_score: number | null
  attempts: number
  locked: boolean
}

export interface QuizInfo {
  quiz_id: string
  title: string
  question_count: number
  pass_threshold: number
  attempts: number
  best_score: number | null
  passed: boolean
  locked: boolean
  lock_reason?: string | null
}

export interface QuizChoice {
  id: string
  text: string
}

export type QuestionType = 'mcq' | 'multi' | 'order' | 'short'

export interface QuizQuestion {
  id: string
  type: QuestionType
  prompt: string
  concept?: string
  difficulty: 1 | 2 | 3
  choices?: QuizChoice[]
}

export interface QuizAttempt {
  hints?: Record<string, Array<{ level: number; hint: string }>>
  attempt_id: string
  attempt_no: number
  questions: QuizQuestion[]
}

/** mcq: choice id, multi: choice ids, order: ordered choice ids, short: free text. */
export type QuizAnswer = string | string[]

export interface QuizEvidence {
  citation: string
  path?: string
  start_line?: number | null
  end_line?: number | null
}

export interface QuizQuestionResult {
  question_id: string
  /** null means the answer could not be graded automatically. */
  correct: boolean | null
  score: number
  explanation: string
  correct_answer?: string[]
  evidence: QuizEvidence[]
  concept?: string
  feedback?: string
  graded_by: 'exact' | 'llm' | 'keywords'
}

export interface AchievementBrief {
  badge: string
  title: string
}

export interface QuizResult {
  attempt_id: string
  score: number
  passed: boolean
  pass_threshold: number
  xp_delta: number
  xp: number
  item_completed: boolean
  next_unlocked: string | null
  results: QuizQuestionResult[]
  weak_concepts: Array<{ concept: string; name: string }>
  review: Array<{ title: string; path?: string; citation?: string }>
  achievements: AchievementBrief[]
}

export interface QuizListEntry {
  item_id: string
  module_id: string
  title: string
  question_count: number
  pass_threshold: number
  attempts: number
  best_score: number | null
  passed: boolean
  locked: boolean
}

/* ---------- Gamification and analytics ---------- */
export interface Achievement {
  badge: string
  title: string
  description: string
  earned_at: string
  user_id?: string
  display_name?: string
}

export interface KnowledgeGap {
  concept: string
  name: string
  avg_score: number
  learners: number
  attempts: number
  weak_prompts: string[]
}

export interface KnowledgeGapsResponse {
  gaps: KnowledgeGap[]
}

export interface LearnerAnalytics {
  user_id: string
  display_name: string
  quizzes_passed: number
  quizzes_attempted: number
  avg_score: number
  mastery: Array<{ topic: string; score: number }>
}

export interface QuizAnalytics {
  item_id: string
  path_id: string
  title: string
  attempts: number
  pass_rate: number
  avg_score: number
}

export interface ResourceAnalytics {
  url: string
  title: string
  resource_type: string | null
  sessions: number
  completed: number
  completion_rate: number
  avg_progress: number
}

export interface ProjectAnalytics {
  learners: LearnerAnalytics[]
  quizzes: QuizAnalytics[]
  resources: ResourceAnalytics[]
  last_activity: Record<string, string>
}
