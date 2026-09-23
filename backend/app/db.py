from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .config import settings


class DBRow(dict):
    """Mapping row with compatibility integer indexing for legacy service calls.

    The service layer historically used both row['column'] and row[0].  Keeping
    this tiny compatibility object lets the persistence migration stay isolated
    while all storage is now PostgreSQL-native.
    """

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class ResultProxy:
    def __init__(self, cursor: psycopg.Cursor):
        self._cursor = cursor

    @staticmethod
    def _row(row: Any) -> DBRow | None:
        if row is None:
            return None
        return DBRow(row)

    def fetchone(self) -> DBRow | None:
        return self._row(self._cursor.fetchone())

    def fetchall(self) -> list[DBRow]:
        return [DBRow(r) for r in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def __iter__(self):
        for row in self._cursor:
            yield DBRow(row)



def _qmark_to_pyformat(sql: str) -> str:
    """Translate legacy qmark bind markers to psycopg '%s'.

    The parser intentionally ignores question marks inside quoted SQL strings.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                # SQL escapes quotes by doubling them.
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            out.append(ch)
        elif ch == '?':
            out.append('%s')
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def _translate_sql(sql: str) -> str:
    statement = sql.strip()
    if re.match(r'(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b', statement):
        statement = re.sub(r'(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', statement, count=1)
        if ' ON CONFLICT ' not in statement.upper():
            statement = statement.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    if re.match(r'(?is)^INSERT\s+OR\s+REPLACE\s+INTO\b', statement):
        raise RuntimeError('INSERT OR REPLACE is not supported; use PostgreSQL ON CONFLICT explicitly.')
    return _qmark_to_pyformat(statement)


class ConnectionProxy:
    def __init__(self, conn: psycopg.Connection):
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> ResultProxy:
        translated = _translate_sql(sql)
        cursor = self._conn.execute(translated) if params is None else self._conn.execute(translated, params)
        return ResultProxy(cursor)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()



def _raw_connect(*, autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        autocommit=autocommit,
        connect_timeout=settings.database_connect_timeout_s,
        application_name='spartan-studybuddy',
    )
    if settings.database_statement_timeout_ms > 0:
        conn.execute(f"SET statement_timeout = {int(settings.database_statement_timeout_ms)}")
    return conn


def _connect() -> ConnectionProxy:
    conn = _raw_connect()
    # The extension is created by init_db/startup. Register adapters on every
    # application connection so Python lists/numpy arrays map to vector values.
    register_vector(conn)
    return ConnectionProxy(conn)


@contextmanager
def db() -> Iterator[ConnectionProxy]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _schema_statements() -> list[str]:
    dim = int(settings.embedding_dim)
    return [
        '''CREATE TABLE IF NOT EXISTS organizations(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), display_name TEXT NOT NULL, email TEXT,
          role_title TEXT, avatar TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS invites(
          id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), email TEXT, role_title TEXT,
          token TEXT UNIQUE NOT NULL, invited_by TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, accepted_at TIMESTAMPTZ
        )''',
        '''CREATE TABLE IF NOT EXISTS projects(
          id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES organizations(id), name TEXT NOT NULL, description TEXT DEFAULT '',
          source_uri TEXT, default_branch TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS project_members(
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role TEXT NOT NULL DEFAULT 'learner', joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(project_id,user_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS sources(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, name TEXT NOT NULL, uri TEXT, status TEXT NOT NULL DEFAULT 'ready',
          metadata_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS indexed_documents(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, source_id TEXT,
          source_type TEXT NOT NULL, source_name TEXT NOT NULL, source_uri TEXT, mime_type TEXT, language TEXT,
          content_hash TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        'CREATE INDEX IF NOT EXISTS idx_docs_project ON indexed_documents(project_id)',
        f'''CREATE TABLE IF NOT EXISTS indexed_chunks(
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES indexed_documents(id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL,
          kind TEXT NOT NULL DEFAULT 'text', symbol TEXT, start_line INTEGER, end_line INTEGER,
          content TEXT NOT NULL, topic TEXT, metadata_json TEXT NOT NULL DEFAULT '{{}}',
          embedding vector({dim}),
          search_tsv tsvector GENERATED ALWAYS AS (
            to_tsvector('simple'::regconfig,
              coalesce(content,'') || ' ' || coalesce(symbol,'') || ' ' || coalesce(topic,''))
          ) STORED
        )''',
        'CREATE INDEX IF NOT EXISTS idx_chunks_project ON indexed_chunks(project_id)',
        'CREATE INDEX IF NOT EXISTS idx_chunks_search_tsv ON indexed_chunks USING GIN(search_tsv)',
        'CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON indexed_chunks USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL',
        '''CREATE TABLE IF NOT EXISTS code_symbols(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          document_id TEXT NOT NULL REFERENCES indexed_documents(id) ON DELETE CASCADE, name TEXT NOT NULL,
          qualified_name TEXT, kind TEXT, language TEXT, start_line INTEGER, end_line INTEGER,
          signature TEXT, docstring TEXT, metadata_json TEXT NOT NULL DEFAULT '{}'
        )''',
        'CREATE INDEX IF NOT EXISTS idx_symbols_project_name ON code_symbols(project_id, name)',
        '''CREATE TABLE IF NOT EXISTS code_edges(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          document_id TEXT REFERENCES indexed_documents(id) ON DELETE CASCADE,
          source_symbol TEXT NOT NULL, target_symbol TEXT NOT NULL, edge_type TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}'
        )''',
        'ALTER TABLE code_edges ADD COLUMN IF NOT EXISTS document_id TEXT REFERENCES indexed_documents(id) ON DELETE CASCADE',
        'CREATE INDEX IF NOT EXISTS idx_edges_project ON code_edges(project_id)',
        '''CREATE TABLE IF NOT EXISTS learning_events(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, source TEXT NOT NULL, type TEXT NOT NULL,
          resource_id TEXT, context_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        'CREATE INDEX IF NOT EXISTS idx_events_user_project ON learning_events(user_id,project_id,created_at DESC)',
        '''CREATE TABLE IF NOT EXISTS resource_sessions(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, resource_url TEXT NOT NULL,
          resource_title TEXT, resource_type TEXT, seconds_active DOUBLE PRECISION NOT NULL DEFAULT 0,
          progress DOUBLE PRECISION NOT NULL DEFAULT 0, last_position DOUBLE PRECISION NOT NULL DEFAULT 0,
          duration DOUBLE PRECISION, summary TEXT, concepts_json TEXT NOT NULL DEFAULT '[]',
          checkpoint_json TEXT NOT NULL DEFAULT '[]', last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE NULLS NOT DISTINCT (user_id,project_id,resource_url)
        )''',
        '''CREATE TABLE IF NOT EXISTS mastery(
          user_id TEXT NOT NULL, project_id TEXT NOT NULL, topic TEXT NOT NULL,
          score DOUBLE PRECISION NOT NULL DEFAULT 0, confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
          evidence_json TEXT NOT NULL DEFAULT '[]', updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id, project_id, topic)
        )''',
        '''CREATE TABLE IF NOT EXISTS memory_items(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, kind TEXT NOT NULL,
          title TEXT NOT NULL, content TEXT NOT NULL, importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
          metadata_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        'CREATE INDEX IF NOT EXISTS idx_memory_user_project ON memory_items(user_id,project_id,importance DESC)',
        '''CREATE TABLE IF NOT EXISTS chat_threads(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, title TEXT NOT NULL,
          mode TEXT NOT NULL DEFAULT 'auto', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS chat_messages(
          id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
          role TEXT NOT NULL, content TEXT NOT NULL, sources_json TEXT NOT NULL DEFAULT '[]', route TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS roadmaps(
          id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL, goal TEXT NOT NULL, description TEXT DEFAULT '', is_public INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS roadmap_items(
          id TEXT PRIMARY KEY, roadmap_id TEXT NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE,
          position INTEGER NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'lesson', resource_url TEXT,
          source TEXT, estimated_minutes INTEGER DEFAULT 15, metadata_json TEXT NOT NULL DEFAULT '{}'
        )''',
        '''CREATE TABLE IF NOT EXISTS roadmap_members(
          roadmap_id TEXT NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE, user_id TEXT NOT NULL,
          xp INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(roadmap_id,user_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS roadmap_resources(
          id TEXT PRIMARY KEY, roadmap_id TEXT NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE,
          title TEXT NOT NULL, url TEXT NOT NULL, resource_type TEXT, source TEXT, rationale TEXT,
          order_index INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS progress(
          user_id TEXT NOT NULL, roadmap_item_id TEXT NOT NULL REFERENCES roadmap_items(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'not_started', progress DOUBLE PRECISION NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,roadmap_item_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS onboarding_paths(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          creator_id TEXT NOT NULL, title TEXT NOT NULL, target_role TEXT NOT NULL, level TEXT NOT NULL,
          weeks INTEGER NOT NULL DEFAULT 4, hours_per_week INTEGER NOT NULL DEFAULT 8,
          is_public INTEGER NOT NULL DEFAULT 0, invite_code TEXT UNIQUE, plan_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS onboarding_members(
          path_id TEXT NOT NULL REFERENCES onboarding_paths(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL, xp INTEGER NOT NULL DEFAULT 0, progress DOUBLE PRECISION NOT NULL DEFAULT 0,
          streak INTEGER NOT NULL DEFAULT 0, joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(path_id, user_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS path_progress(
          path_id TEXT NOT NULL REFERENCES onboarding_paths(id) ON DELETE CASCADE, user_id TEXT NOT NULL,
          item_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_started', progress DOUBLE PRECISION NOT NULL DEFAULT 0,
          score DOUBLE PRECISION, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(path_id,user_id,item_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS path_resources(
          id TEXT PRIMARY KEY, path_id TEXT NOT NULL REFERENCES onboarding_paths(id) ON DELETE CASCADE,
          module_id TEXT, title TEXT NOT NULL, url TEXT NOT NULL, resource_type TEXT, source TEXT,
          rationale TEXT, estimated_minutes INTEGER DEFAULT 15, metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS achievements(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, badge TEXT NOT NULL, title TEXT NOT NULL,
          description TEXT, earned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS agent_jobs(
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, kind TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', payload_json TEXT NOT NULL DEFAULT '{}', result_json TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS agent_traces(
          id TEXT PRIMARY KEY, user_id TEXT, project_id TEXT, thread_id TEXT, agent TEXT NOT NULL,
          route TEXT, model TEXT, prompt_preview TEXT, response_preview TEXT, retrieved_json TEXT NOT NULL DEFAULT '[]',
          latency_ms DOUBLE PRECISION, ttft_ms DOUBLE PRECISION, input_tokens INTEGER, output_tokens INTEGER,
          tokens_per_second DOUBLE PRECISION, success INTEGER NOT NULL DEFAULT 1, metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''',
        'CREATE INDEX IF NOT EXISTS idx_traces_created ON agent_traces(created_at DESC)',
    ]


def init_db() -> None:
    # Bootstrap the extension first, then register the vector adapter and create
    # the complete schema. This is idempotent and safe to run on every startup.
    with _raw_connect(autocommit=True) as conn:
        conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        register_vector(conn)
        for statement in _schema_statements():
            conn.execute(statement)

        conn.execute(
            'INSERT INTO organizations(id,name) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING',
            (settings.demo_org_id, 'Aperture Engineering'),
        )
        conn.execute(
            '''INSERT INTO users(id,org_id,display_name,email,role_title,avatar)
               VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING''',
            (settings.demo_user_id, settings.demo_org_id, 'Alex Morgan', 'alex@aperture.local', 'ML Engineer', 'AM'),
        )


def database_health() -> dict[str, Any]:
    try:
        with _raw_connect(autocommit=True) as conn:
            row = conn.execute(
                "SELECT current_database() AS database, current_setting('server_version') AS version, "
                "EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector') AS pgvector"
            ).fetchone()
            return {'ok': True, **dict(row or {})}
    except Exception as exc:
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
