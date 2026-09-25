from __future__ import annotations
import json,re,time
from dataclasses import dataclass
from typing import Any
import httpx
from ..config import settings
from .telemetry import MODEL_REQUESTS,MODEL_LATENCY,MODEL_TTFT,MODEL_OUTPUT_TPS,trace

_SENT_SPLIT=re.compile(r'(?<=[.!?])\s+')
_THINK_STRIP=re.compile(r'^.*?</think>\s*',re.S)

def _strip_thinking(text:str)->str:
    """Remove the model's own <think>...</think> reasoning block from the visible answer.
    No --reasoning-parser is configured for this qwen3_5 architecture in vLLM, so the raw block
    comes back inline in the completion text; strip it in application code instead."""
    return _THINK_STRIP.sub('',text,count=1)

def _dedupe_repetition(text:str,min_words:int=4)->str:
    """Cut a response at its first near-duplicate sentence.
    Measured root cause: this model reliably loops a trailing sentence/paragraph verbatim until
    max_tokens specifically when chat_template_kwargs.enable_thinking is False (reproduced on two
    vLLM versions and with/without speculative decoding); it stops cleanly when thinking is left
    on. We now leave thinking on and strip the <think> block above, but keep this as a deterministic
    safety net -- sampling-parameter tuning (temperature, repetition_penalty, frequency_penalty)
    was tested separately and did not reliably prevent the loop on its own."""
    seen=set();cursor=0
    for s in _SENT_SPLIT.split(text):
        norm=re.sub(r'\s+',' ',s).strip().lower()
        if len(norm.split())>=min_words:
            if norm in seen:return text[:cursor].rstrip()
            seen.add(norm)
        idx=text.find(s,cursor)
        if idx==-1:break
        cursor=idx+len(s)
    return text

@dataclass
class Completion:
    text:str
    route:str
    model:str
    latency_ms:float
    ttft_ms:float|None
    input_tokens:int|None
    output_tokens:int|None
    tokens_per_second:float|None
    success:bool=True

class ModelRouter:
    def __init__(self):
        self.routes={
            'instruct':(settings.vllm_instruct_url,settings.vllm_instruct_model),
            'reasoning':(settings.vllm_reasoning_url,settings.vllm_reasoning_model),
            'code':(settings.vllm_reasoning_url,settings.vllm_reasoning_model),
            # Cheap/fast tasks (resource-resume summaries, short classification) reuse the same
            # 8B model already deployed for browser-use, instead of the heavier Socratic-tuned model.
            'light':(settings.vllm_browser_url,settings.vllm_browser_model),
        }
    async def endpoint_health(self)->dict[str,bool]:
        out={}
        async with httpx.AsyncClient(timeout=2) as c:
            for name,(base,_) in self.routes.items():
                try: out[name]=(await c.get(base.rstrip('/')+'/models',headers={'Authorization':f'Bearer {settings.vllm_api_key}'})).is_success
                except Exception: out[name]=False
            try: out['embeddings']=(await c.get(settings.embedding_url.rstrip('/')+'/models',headers={'Authorization':f'Bearer {settings.vllm_api_key}'})).status_code<500
            except Exception: out['embeddings']=False
        return out

    async def generate(self,*,system:str,user:str,tier:str='instruct',temperature:float=.22,max_tokens:int=1400,user_id:str|None=None,project_id:str|None=None,thread_id:str|None=None,agent:str='assistant',retrieved:list|None=None,metadata:dict|None=None,enable_thinking:bool=True)->Completion:
        base,model=self.routes.get(tier,self.routes['instruct'])
        payload={
            'model':model,
            'messages':[{'role':'system','content':system},{'role':'user','content':user}],
            'temperature':temperature,'max_tokens':max_tokens,'stream':True,
            'stream_options':{'include_usage':True},
        }
        # Free-form/open-ended completions (chat, tutoring) default to thinking ON: with it off, this
        # model reliably falls into a verbatim repetition loop that runs to max_tokens (measured on
        # two vLLM versions, with/without speculative decoding). No --reasoning-parser is configured
        # for this qwen3_5 architecture, so vLLM can't split the <think> block into its own field the
        # way it does for supported reasoning models; we strip it out of the raw completion ourselves.
        #
        # Structured JSON extraction (json()/json_with_status()) instead passes enable_thinking=False:
        # tested directly against this model/prompt shape and it produced clean, directly-JSON output
        # with no repetition -- unlike open-ended chat, a JSON object has a natural stop condition (the
        # closing brace), and thinking's own reasoning was observed to loop through self-revisions
        # ("let me make these more specific" repeated verbatim, redrafting the same content) that ate
        # an entire multi-thousand-token budget before ever reaching the answer on large structured
        # tasks (e.g. an 8-module curriculum skeleton) -- with thinking off that entire failure mode
        # disappears and generation is also markedly faster (no reasoning tokens to pay for).
        payload['chat_template_kwargs']={'enable_thinking':enable_thinking}
        started=time.perf_counter(); first=None; pieces=[]; usage={}; success=True
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
                async with client.stream('POST',base.rstrip('/')+'/chat/completions',json=payload,headers={'Authorization':f'Bearer {settings.vllm_api_key}'}) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'): continue
                        raw=line[5:].strip()
                        if not raw or raw=='[DONE]': continue
                        try:data=json.loads(raw)
                        except Exception:continue
                        if data.get('usage'): usage=data['usage'] or usage
                        for choice in data.get('choices') or []:
                            delta=(choice.get('delta') or {}).get('content')
                            if delta:
                                if first is None:first=time.perf_counter()
                                pieces.append(delta)
            text=_dedupe_repetition(_strip_thinking(''.join(pieces).strip()))
            if not text:
                success=False
                text='The local model did not return a response. Please retry.'
        except Exception as exc:
            success=False
            text=("Let's reason from the evidence instead of jumping to the final answer. What part of the code path or documentation seems most relevant first?" if 'socratic' in system.lower() else f'Local model unavailable: {type(exc).__name__}. Start the DGX model stack with `make models`.')
        ended=time.perf_counter(); latency=ended-started; ttft=(first-started if first else None)
        out_tok=usage.get('completion_tokens'); in_tok=usage.get('prompt_tokens')
        decode_s=(ended-first) if first else None
        tps=(out_tok/decode_s if out_tok and decode_s and decode_s>0 else None)
        route=tier
        MODEL_REQUESTS.labels(route, str(success).lower()).inc(); MODEL_LATENCY.labels(route).observe(latency)
        if ttft is not None: MODEL_TTFT.labels(route).observe(ttft)
        if tps is not None: MODEL_OUTPUT_TPS.labels(route).observe(tps)
        trace(user_id=user_id,project_id=project_id,thread_id=thread_id,agent=agent,route=route,model=model,prompt=user,response=text,retrieved=retrieved,latency_ms=latency*1000,ttft_ms=ttft*1000 if ttft is not None else None,input_tokens=in_tok,output_tokens=out_tok,tps=tps,success=success,metadata=metadata)
        return Completion(text,route,model,latency*1000,ttft*1000 if ttft is not None else None,in_tok,out_tok,tps,success)

    async def complete(self,**kwargs)->str:
        return (await self.generate(**kwargs)).text

    async def json_with_status(self,*,system:str,user:str,tier:str='reasoning',fallback:dict[str,Any]|None=None,max_tokens:int=2600,enable_thinking:bool=False,**kwargs)->tuple[dict[str,Any],str]:
        result=await self.generate(system=system+'\nReturn only valid JSON. No markdown fences.',user=user,tier=tier,temperature=.12,max_tokens=max_tokens,enable_thinking=enable_thinking,**kwargs)
        try:
            # Parse the first balanced JSON value and ignore anything after it, instead of a greedy
            # '{.*}' regex spanning first-'{' to last-'}': measured a real, otherwise-valid skeleton
            # response get thrown away by that regex because the model appended one stray extra '}'
            # at the very end ('...}]}}' instead of '...}]}') -- the regex's own greedy match included
            # that trailing brace as "the JSON", so json.loads saw trailing data and raised, and a good
            # generation silently became a fallback. raw_decode stops at the end of the first valid
            # value and never looks at what follows, so trailing junk (or leading prose) can't break it.
            start=result.text.index('{')
            parsed,_=json.JSONDecoder().raw_decode(result.text,start)
            if not isinstance(parsed,dict):raise ValueError('JSON response must be an object')
            return parsed,'generated'
        except Exception:
            return (fallback or {'raw':result.text}),'fallback'

    async def json(self,*,system:str,user:str,tier:str='reasoning',fallback:dict[str,Any]|None=None,max_tokens:int=2600,**kwargs)->dict[str,Any]:
        parsed,_=await self.json_with_status(system=system,user=user,tier=tier,fallback=fallback,max_tokens=max_tokens,**kwargs)
        return parsed

router=ModelRouter()
