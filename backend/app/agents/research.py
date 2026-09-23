from __future__ import annotations
from ..services.jobs import create_job

def start_research(user_id:str,project_id:str,query:str)->dict:
    # Public-web research is delegated to the Mac Browser-Use bridge; only the sanitized user query goes out.
    return create_job(user_id,'web_research',{'query':query,'instruction':'Research authoritative public sources. Return title,url,source_type,summary,why_it_matters. Do not upload private repository context.'},project_id)
