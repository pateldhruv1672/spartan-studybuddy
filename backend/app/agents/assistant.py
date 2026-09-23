from __future__ import annotations
import json,re
from typing import Any
from ..services.retrieval import retrieve,format_context
from ..services.model_router import router
from ..services.memory import memories,add_memory
from ..services.chats import ensure_thread,add_message

SOCRATIC_POLICY='''[MODE:SOCRATIC] You are Spartan StudyBuddy, a Socratic engineering tutor for company onboarding.
Your job is to help the learner reason, not to dump a solution. Ground every codebase claim in supplied evidence.
Use progressive hints: (1) question/nudge, (2) concept reminder, (3) point at code/doc evidence, (4) pseudocode/structure, (5) final answer only if explicitly allowed.
When the user is doing an assessment or asks to fix code, do not provide a paste-ready final implementation unless allow_final_answer is true.
Be warm, concise and technically rigorous. End with one concrete question or next action. Cite evidence with [n] markers from context.'''
QA_POLICY='''[MODE:DIRECT] You are Spartan StudyBuddy, an enterprise codebase and documentation assistant. Answer the user's question directly and clearly from the supplied private evidence. It is okay to give direct answers in this mode. Distinguish what the repository proves from general background knowledge. Cite evidence using [n] markers. If evidence is insufficient, say what is missing rather than inventing it.'''
EXPLAIN_POLICY='''[MODE:EXPLAIN] Explain the requested concept like a superb technical mentor. Start with a plain-language mental model, then connect it to the company's actual code/docs, then give a small example and a 2-question self-check. Avoid jargon until it is defined. Cite supplied evidence with [n].'''
CODE_POLICY='''[MODE:DIRECT] You are a senior engineer onboarding a teammate into a private codebase. Explain code paths, interfaces, side effects, dependencies, tests and failure modes using repository evidence. Directly answer factual code questions. If the request is to complete an assessment, switch to progressive hints instead of writing the final solution. Cite supplied evidence with [n].'''

def choose_mode(question:str,requested:str='auto',current_code:str|None=None)->str:
    if requested!='auto': return requested
    q=question.lower()
    if any(x in q for x in ['give me a hint','guide me','don\'t give','do not give','socratic','help me figure','stuck on','teach me by']): return 'socratic'
    if any(x in q for x in ['explain simply','eli5','simple terms','teach me this concept','what does this mean']): return 'explain'
    if current_code or any(x in q for x in ['function','class','method','code path','call path','where is','implementation','why does this code']): return 'code'
    if any(x in q for x in ['research','compare recent','state of the art','latest papers']): return 'research'
    return 'qa'

async def ask(*,user_id:str,project_id:str,question:str,thread_id:str|None=None,mode:str='auto',current_code:str|None=None,file_path:str|None=None,hint_level:int=1,allow_final_answer:bool=False)->dict[str,Any]:
    route=choose_mode(question,mode,current_code)
    if route=='research':
        from .research import start_research
        return {'mode':'research','research_job':start_research(user_id,project_id,question)}
    thread_id=ensure_thread(user_id,project_id,title=question[:72] or 'StudyBuddy',mode=route,thread_id=thread_id)
    add_message(thread_id,'user',question,[],route)
    evidence=await retrieve(project_id,question,top_k=10,rerank=True,include_graph=True)
    context=format_context(evidence)
    memory=memories(user_id,project_id,10)
    memory_text='\n'.join(f"- {m['kind']}: {m['title']} — {m['content'][:400]}" for m in memory)
    code_note=f'\nCurrent editor file: {file_path}\nCurrent selection/code:\n{(current_code or "")[:8000]}' if current_code else ''
    if route=='socratic':
        system=SOCRATIC_POLICY+f'\nCurrent hint level: {hint_level}/5. Final answer allowed: {allow_final_answer}.'
        tier='reasoning'
    elif route=='explain': system=EXPLAIN_POLICY; tier='instruct'
    elif route=='code': system=CODE_POLICY; tier='code'
    else: system=QA_POLICY; tier='instruct'
    prompt=f'''Question: {question}

PRIVATE EVIDENCE:
{context or '(No matching indexed evidence.)'}

LEARNER MEMORY:
{memory_text or '(No saved learner memory yet.)'}
{code_note}

Answer in the selected mode: {route}.'''
    result=await router.generate(system=system,user=prompt,tier=tier,max_tokens=1500,user_id=user_id,project_id=project_id,thread_id=thread_id,agent=f'{route}_assistant',retrieved=[{'citation':x.get('citation'),'source':x.get('source_name'),'symbol':x.get('symbol')} for x in evidence],metadata={'mode':route,'hint_level':hint_level})
    sources=[{'ref':x.get('ref'),'citation':x.get('citation'),'source_name':x.get('source_name'),'source_uri':x.get('source_uri'),'symbol':x.get('symbol'),'start_line':x.get('start_line'),'end_line':x.get('end_line')} for x in evidence]
    add_message(thread_id,'assistant',result.text,sources,route)
    # Persist compact episodic memory, not raw full prompts.
    if route in {'socratic','code','explain'}:
        add_memory(user_id,project_id,'conversation',question[:90],result.text[:900],.35,{'route':route,'thread_id':thread_id})
    return {'answer':result.text,'mode':route,'thread_id':thread_id,'sources':sources,'metrics':{'latency_ms':result.latency_ms,'ttft_ms':result.ttft_ms,'output_tokens':result.output_tokens,'tokens_per_second':result.tokens_per_second}}
