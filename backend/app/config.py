from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env', override=False)
DATA_DIR = Path(os.getenv('STUDYBUDDY_DATA_DIR', ROOT / 'data')).expanduser().resolve()
for p in (DATA_DIR, DATA_DIR/'repos', DATA_DIR/'uploads', DATA_DIR/'cache', DATA_DIR/'exports'):
    p.mkdir(parents=True, exist_ok=True)

@dataclass(frozen=True)
class Settings:
    app_name: str = 'Spartan StudyBuddy for Teams'
    host: str = os.getenv('STUDYBUDDY_HOST', '0.0.0.0')
    port: int = int(os.getenv('STUDYBUDDY_PORT', '8000'))
    database_url: str = os.getenv('DATABASE_URL', 'postgresql://studybuddy:studybuddy@127.0.0.1:5432/studybuddy')
    database_connect_timeout_s: int = int(os.getenv('DATABASE_CONNECT_TIMEOUT_S', '10'))
    database_statement_timeout_ms: int = int(os.getenv('DATABASE_STATEMENT_TIMEOUT_MS', '120000'))
    repos_dir: Path = DATA_DIR / 'repos'
    uploads_dir: Path = DATA_DIR / 'uploads'
    demo_user_id: str = os.getenv('STUDYBUDDY_DEMO_USER', 'demo-spartan')
    demo_org_id: str = os.getenv('STUDYBUDDY_DEMO_ORG', 'demo-company')
    cors_origins: str = os.getenv('STUDYBUDDY_CORS', 'http://127.0.0.1:8000,http://localhost:8000')
    api_token: str = os.getenv('STUDYBUDDY_API_TOKEN', 'spartan-local')
    bridge_token: str = os.getenv('STUDYBUDDY_BRIDGE_TOKEN', '')
    auth_secret: str = os.getenv('STUDYBUDDY_AUTH_SECRET', '')
    auth_token_ttl_hours: int = int(os.getenv('STUDYBUDDY_AUTH_TTL_HOURS', '12'))
    # 0 (default): a public sign-up as MANAGER creates a brand-new organisation for that person (they cannot join or take over an existing one).
    # 1: legacy/demo behaviour - a manager sign-up may target an existing organisation (only for closed demos).
    open_manager_signup: bool = os.getenv('STUDYBUDDY_OPEN_MANAGER_SIGNUP', '0') == '1'
    require_auth: bool = os.getenv('STUDYBUDDY_REQUIRE_AUTH', '1') == '1'   # secure by default; set 0 only for an isolated demo
    max_upload_mb: int = int(os.getenv('MAX_UPLOAD_MB', '250'))
    max_remote_mb: int = int(os.getenv('MAX_REMOTE_MB', '25'))
    request_timeout_s: float = float(os.getenv('MODEL_TIMEOUT_S', '180'))

    # One stable OpenAI-compatible model name is used by the product. The serving script maps it
    # to the base checkpoint before training and the merged tuned checkpoint afterwards.
    vllm_instruct_url: str = os.getenv('VLLM_INSTRUCT_URL', 'http://127.0.0.1:8101/v1')
    vllm_instruct_model: str = os.getenv('VLLM_INSTRUCT_MODEL', 'spartan-teacher')
    vllm_reasoning_url: str = os.getenv('VLLM_REASONING_URL', os.getenv('VLLM_INSTRUCT_URL', 'http://127.0.0.1:8101/v1'))
    vllm_reasoning_model: str = os.getenv('VLLM_REASONING_MODEL', os.getenv('VLLM_INSTRUCT_MODEL', 'spartan-teacher'))
    vllm_api_key: str = os.getenv('VLLM_API_KEY', 'local-edge')

    embedding_url: str = os.getenv('EMBEDDING_URL', 'http://127.0.0.1:8105/v1')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', 'Qwen/Qwen3-Embedding-0.6B')
    embedding_dim: int = int(os.getenv('EMBEDDING_DIM', '1024'))
    embedding_batch: int = int(os.getenv('EMBEDDING_BATCH', '24'))
    # The embedding vLLM container's own configured context window (same env var it's started with);
    # chunking must stay under this or the embedding server rejects the whole batch.
    embedding_max_model_len: int = int(os.getenv('EMBEDDING_MAX_MODEL_LEN', '8192'))
    allow_embedding_fallback: bool = os.getenv('ALLOW_EMBEDDING_FALLBACK', '0') == '1'
    retrieval_top_k: int = int(os.getenv('RETRIEVAL_TOP_K', '12'))

    browser_llm_provider: str = os.getenv('BROWSER_LLM_PROVIDER', 'vllm').lower()
    vllm_browser_url: str = os.getenv('VLLM_BROWSER_URL', os.getenv('VLLM_INSTRUCT_URL', 'http://127.0.0.1:8101/v1'))
    vllm_browser_model: str = os.getenv('VLLM_BROWSER_MODEL', os.getenv('VLLM_INSTRUCT_MODEL', 'spartan-teacher'))
    ollama_browser_url: str = os.getenv('OLLAMA_BROWSER_URL', 'http://127.0.0.1:11434/v1')
    ollama_browser_model: str = os.getenv('OLLAMA_BROWSER_MODEL', 'qwen3:8b')

    github_token: str = os.getenv('GITHUB_TOKEN', '')
    google_access_token: str = os.getenv('GOOGLE_DRIVE_ACCESS_TOKEN', '')
    telemetry_enabled: bool = os.getenv('TELEMETRY_ENABLED','1') == '1'
    trace_content: bool = os.getenv('STUDYBUDDY_TRACE_CONTENT','0') == '1'
    langsmith_api_key: str = os.getenv('LANGSMITH_API_KEY','')
    langsmith_project: str = os.getenv('LANGSMITH_PROJECT','spartan-studybuddy')

    @property
    def browser_model_url(self) -> str:
        return self.ollama_browser_url if self.browser_llm_provider == 'ollama' else self.vllm_browser_url
    @property
    def browser_model_name(self) -> str:
        return self.ollama_browser_model if self.browser_llm_provider == 'ollama' else self.vllm_browser_model

settings = Settings()
