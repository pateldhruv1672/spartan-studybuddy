from __future__ import annotations
import json,time
from typing import Any
from ..db import db
from .indexer import hybrid_search
from .model_router import router
from .telemetry import RAG_SEARCH

async def retrieve(project_id:str,query:str,top_k:int=10,rerank:bool=True,include_graph:bool=True)->list[dict[str,Any]]:
    started=time.perf_counter(); candidates=hybrid_search(project_id,query,max(top_k*2,16))
    if include_graph:
        terms=[x for x in query.replace('(',' ').replace(')',' ').replace('.',' ').split() if len(x)>2][:12]
        with db() as conn:
            for term in terms:
                rows=conn.execute('''SELECT s.name,s.qualified_name,s.kind,s.start_line,s.end_line,d.source_name,d.source_uri,d.language,c.content,c.id
                  FROM code_symbols s JOIN indexed_documents d ON d.id=s.document_id
                  LEFT JOIN indexed_chunks c ON c.document_id=s.document_id AND c.symbol=s.name
                  WHERE s.project_id=? AND (s.name LIKE ? OR s.qualified_name LIKE ?) LIMIT 4''',(project_id,f'%{term}%',f'%{term}%')).fetchall()
                for r in rows:
                    d=dict(r); cid=d.pop('id') or f"symbol:{d['source_name']}:{d['name']}"
                    if not any(x.get('id')==cid for x in candidates):
                        d.update({'id':cid,'symbol':d.get('qualified_name') or d.get('name'),'kind':'code','rrf':.01,'citation':f"{d['source_name']}:{d.get('start_line') or '?'}-{d.get('end_line') or '?'}"})
                        candidates.append(d)
    candidates=candidates[:max(top_k*2,18)]
    if rerank and len(candidates)>top_k:
        compact=[{'i':i,'source':x.get('source_name'),'symbol':x.get('symbol'),'kind':x.get('kind'),'text':(x.get('content') or '')[:700]} for i,x in enumerate(candidates)]
        fallback={'order':list(range(min(top_k,len(candidates))))}
        ranked=await router.json(system='You are a retrieval reranker. Rank evidence by usefulness for answering the query. Prefer exact code symbols, tests, architecture docs and direct definitions. Return {"order":[integer indexes]}.',user=f'Query: {query}\nCandidates: {json.dumps(compact)}',tier='instruct',fallback=fallback,agent='rag_reranker',project_id=project_id,metadata={'candidate_count':len(candidates)})
        order=[i for i in ranked.get('order',[]) if isinstance(i,int) and 0<=i<len(candidates)]
        seen=set(); selected=[]
        for i in order:
            if i not in seen:selected.append(candidates[i]);seen.add(i)
        for i,x in enumerate(candidates):
            if len(selected)>=top_k:break
            if i not in seen:selected.append(x);seen.add(i)
        candidates=selected[:top_k]
    else:candidates=candidates[:top_k]
    for i,x in enumerate(candidates,1):
        if not x.get('citation'):
            x['citation']=f"{x.get('source_name','source')}:{x.get('start_line') or '?'}-{x.get('end_line') or '?'}"
        x['ref']=f'[{i}]'
    RAG_SEARCH.labels('hybrid_rerank' if rerank else 'hybrid').observe(time.perf_counter()-started)
    return candidates

def format_context(items:list[dict[str,Any]],max_chars:int=18000)->str:
    blocks=[]; total=0
    for x in items:
        text=(x.get('content') or '').strip()
        header=f"{x.get('ref','')} {x.get('citation','')} | {x.get('kind','text')}"
        block=f'{header}\n{text}'
        if total+len(block)>max_chars:break
        blocks.append(block);total+=len(block)
    return '\n\n---\n\n'.join(blocks)
