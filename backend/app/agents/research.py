from __future__ import annotations
import re

from ..db import db
from ..graph import catalog
from ..services.jobs import create_job


def _public_topics(user_id:str,query:str,limit:int=8)->list[str]:
    """Map private wording to catalog IDs locally; only vetted phrases leave the system."""
    words={w for w in re.split(r'[^a-z0-9]+',(query or '').lower()) if len(w)>2}
    scored=[]
    for cid,concept in catalog.concepts().items():
        public=' '.join([concept.get('name',''),concept.get('search_topic',''),*concept.get('keywords',[])])
        overlap=len(words & {w for w in re.split(r'[^a-z0-9]+',public.lower()) if len(w)>2})
        if overlap:scored.append((overlap,cid))
    ids=[cid for _,cid in sorted(scored,key=lambda x:(-x[0],x[1]))]
    if not ids:
        with db() as conn:row=conn.execute('SELECT role_title FROM users WHERE id=?',(user_id,)).fetchone()
        role,_=catalog.match_role(row['role_title'] if row else None)
        ids=list(role['concepts'])
    return catalog.public_search_topics(ids,limit)


def start_research(user_id:str,project_id:str,query:str)->dict:
    topics=_public_topics(user_id,query)
    if not topics:
        raise ValueError('No public-safe research topics could be derived')
    return create_job(user_id,'web_research',{
        'query':'Research these approved public engineering topics: '+', '.join(topics),
        'topics':topics,
        'instruction':'Use only the approved generic topics. Return title,url,source_type,summary,why_it_matters. Never search private identifiers or repository text.',
        'privacy':'catalog_topics_only',
    },project_id)
