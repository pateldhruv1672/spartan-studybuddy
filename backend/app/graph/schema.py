"""PostgreSQL DDL for the knowledge graph, quizzes and attempts.

Everything is idempotent (`IF NOT EXISTS`) and appended to `db._schema_statements()`, so a clean
deployment needs no manual migration. The graph is stored relationally (no extra database engine):
node/edge tables with deterministic ids, so a rebuild keeps ids — and therefore plan/quiz references —
stable for unchanged entities.
"""
from __future__ import annotations


def statements() -> list[str]:
    return [
        # Per-document structural facts extracted at index time (imports, links, mentions, manifest deps).
        '''CREATE TABLE IF NOT EXISTS kg_facts(
          document_id TEXT PRIMARY KEY REFERENCES indexed_documents(id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          facts_json TEXT NOT NULL DEFAULT '{}', partial INTEGER NOT NULL DEFAULT 0,
          extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        'CREATE INDEX IF NOT EXISTS idx_kg_facts_project ON kg_facts(project_id)',
        '''CREATE TABLE IF NOT EXISTS kg_communities(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          name TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', size INTEGER NOT NULL DEFAULT 0,
          keywords_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}',
          summary_source TEXT NOT NULL DEFAULT 'template'
        )''',
        'CREATE INDEX IF NOT EXISTS idx_kg_comm_project ON kg_communities(project_id)',
        '''CREATE TABLE IF NOT EXISTS kg_nodes(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL, path TEXT,
          document_id TEXT, chunk_id TEXT, start_line INTEGER, end_line INTEGER, language TEXT,
          summary TEXT, community_id TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(project_id, kind, key)
        )''',
        'CREATE INDEX IF NOT EXISTS idx_kg_nodes_project_kind ON kg_nodes(project_id, kind)',
        'CREATE INDEX IF NOT EXISTS idx_kg_nodes_doc ON kg_nodes(document_id)',
        '''CREATE TABLE IF NOT EXISTS kg_edges(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL, weight DOUBLE PRECISION NOT NULL DEFAULT 1,
          evidence_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(project_id, src, dst, type)
        )''',
        'CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(project_id, src)',
        'CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(project_id, dst)',
        '''CREATE TABLE IF NOT EXISTS kg_builds(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'running', stats_json TEXT NOT NULL DEFAULT '{}', error TEXT,
          started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ
        )''',
        'CREATE INDEX IF NOT EXISTS idx_kg_builds_project ON kg_builds(project_id, started_at DESC)',
        # Quizzes: one per (path, item). The question bank may be larger than the per-attempt draw.
        '''CREATE TABLE IF NOT EXISTS quizzes(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          path_id TEXT NOT NULL REFERENCES onboarding_paths(id) ON DELETE CASCADE,
          module_id TEXT, item_id TEXT NOT NULL, title TEXT NOT NULL,
          pass_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.7, draw_count INTEGER NOT NULL DEFAULT 5,
          engine TEXT NOT NULL DEFAULT 'deterministic', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(path_id, item_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS quiz_questions(
          id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
          ordinal INTEGER NOT NULL, qtype TEXT NOT NULL, prompt TEXT NOT NULL,
          choices_json TEXT NOT NULL DEFAULT '[]', answer_json TEXT NOT NULL DEFAULT 'null',
          explanation TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]',
          concept TEXT, difficulty INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'graph',
          weight DOUBLE PRECISION NOT NULL DEFAULT 1
        )''',
        'CREATE INDEX IF NOT EXISTS idx_quiz_questions_quiz ON quiz_questions(quiz_id, ordinal)',
        '''CREATE TABLE IF NOT EXISTS quiz_attempts(
          id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL, attempt_no INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'open',
          question_ids_json TEXT NOT NULL DEFAULT '[]', order_json TEXT NOT NULL DEFAULT '{}',
          answers_json TEXT NOT NULL DEFAULT '{}', score DOUBLE PRECISION, passed INTEGER,
          detail_json TEXT NOT NULL DEFAULT '[]',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, submitted_at TIMESTAMPTZ
        )''',
        'CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user ON quiz_attempts(quiz_id, user_id, created_at DESC)',
        "ALTER TABLE quiz_attempts ADD COLUMN IF NOT EXISTS snapshot_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE onboarding_paths ADD COLUMN IF NOT EXISTS configuration_key TEXT",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_onboarding_configuration ON onboarding_paths(configuration_key) WHERE configuration_key IS NOT NULL",
        "ALTER TABLE quiz_attempts ADD COLUMN IF NOT EXISTS hints_json TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS leaderboard_visible BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS metadata_json TEXT NOT NULL DEFAULT '{}'",
        # Invites can pre-assign a workspace (membership is created when the invite is accepted).
        'ALTER TABLE invites ADD COLUMN IF NOT EXISTS project_id TEXT REFERENCES projects(id) ON DELETE SET NULL',
        # Achievements existed in the schema but were never written; one badge per (user, project, badge).
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_achievements_unique ON achievements(user_id, COALESCE(project_id, \'\'), badge)',
    ]
