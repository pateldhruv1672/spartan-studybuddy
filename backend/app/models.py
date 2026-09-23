from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    ok: bool; name: str; database: dict[str,Any]; model_endpoints: dict[str,bool]
class LearningEventIn(BaseModel):
    event_id: str|None=None; user_id: str='demo-spartan'; project_id: str|None=None
    source: Literal['browser','vscode','webapp','research','system']='webapp'; type: str
    resource_id: str|None=None; context: dict[str,Any]=Field(default_factory=dict)
class ProjectCreateRequest(BaseModel):
    org_id: str='demo-company'; user_id: str='demo-spartan'; name: str; description: str=''
class InviteRequest(BaseModel):
    org_id: str='demo-company'; invited_by: str='demo-spartan'; email: str|None=None; role_title: str='Engineer'
class InviteAcceptRequest(BaseModel):
    token: str; display_name: str; email: str|None=None; role_title: str='Engineer'
class SourceIngestRequest(BaseModel):
    user_id: str='demo-spartan'; project_id: str; uri: str; kind: Literal['auto','github','web','gdrive']='auto'
    name: str|None=None; branch: str|None=None; access_token: str|None=None
class TextIndexRequest(BaseModel):
    project_id: str; source_type: str; source_name: str; content: str; source_uri: str|None=None
    mime_type: str|None='text/plain'; language: str|None=None; metadata: dict[str,Any]=Field(default_factory=dict)
class SearchRequest(BaseModel):
    project_id: str; query: str; top_k: int=Field(default=10,ge=1,le=40); filters: dict[str,Any]=Field(default_factory=dict)
class AskRequest(BaseModel):
    user_id: str='demo-spartan'; project_id: str; question: str; thread_id: str|None=None
    mode: Literal['auto','qa','socratic','explain','code','research']='auto'
    current_code: str|None=None; file_path: str|None=None; hint_level: int=Field(default=1,ge=1,le=5)
    allow_final_answer: bool=False
class OnboardingRequest(BaseModel):
    user_id: str='demo-spartan'; project_id: str; target_role: str; level: Literal['junior','mid','senior']='junior'
    weeks: int=Field(default=4,ge=1,le=16); hours_per_week: int=Field(default=8,ge=1,le=40); background: str=''; is_public: bool=False
class ProgressRequest(BaseModel):
    user_id: str='demo-spartan'; item_id: str; status: Literal['not_started','in_progress','completed']; progress: float=Field(default=0,ge=0,le=1); score: float|None=None
class JoinPathRequest(BaseModel):
    user_id: str='demo-spartan'; invite_code: str|None=None
class AgentJobRequest(BaseModel):
    user_id: str='demo-spartan'; project_id: str|None=None; kind: Literal['resource_scout','web_research','open_resource']; payload: dict[str,Any]
class ResourceSessionIn(BaseModel):
    user_id: str='demo-spartan'; project_id: str|None=None; url: str; title: str=''; resource_type: str='web'
    seconds_active: float=0; progress: float=0; last_position: float=0; duration: float|None=None
    visible_text: str|None=None; concepts: list[str]=Field(default_factory=list)
class ResearchRequest(BaseModel):
    user_id: str='demo-spartan'; project_id: str; query: str; depth: Literal['quick','standard','deep']='standard'
