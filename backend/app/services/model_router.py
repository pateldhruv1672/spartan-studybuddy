from __future__ import annotations
import json,re,time
from dataclasses import dataclass
from typing import Any
import httpx
from ..config import settings
from .telemetry import MODEL_REQUESTS,MODEL_LATENCY,MODEL_TTFT,MODEL_OUTPUT_TPS,trace

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

class ModelRouter:
    def __init__(self):
        self.routes={
            'instruct':(settings.vllm_instruct_url,settings.vllm_instruct_model),
            'reasoning':(settings.vllm_reasoning_url,settings.vllm_reasoning_model),
            'code':(settings.vllm_reasoning_url,settings.vllm_reasoning_model),
        }
    async def endpoint_health(self)->dict[str,bool]:
        out={}
        async with httpx.AsyncClient(timeout=2) as c:
            for name,(base,_) in self.routes.items():
                try: out[name]=(await c.get(base.rstrip('/')+'/models',headers={'Authorization':f'Bearer {settings.vllm_api_key}'})).status_code<500
                except Exception: out[name]=False
            try: out['embeddings']=(await c.get(settings.embedding_url.rstrip('/')+'/models',headers={'Authorization':f'Bearer {settings.vllm_api_key}'})).status_code<500
            except Exception: out['embeddings']=False
        return out

    async def generate(self,*,system:str,user:str,tier:str='instruct',temperature:float=.22,max_tokens:int=1400,user_id:str|None=None,project_id:str|None=None,thread_id:str|None=None,agent:str='assistant',retrieved:list|None=None,metadata:dict|None=None)->Completion:
        base,model=self.routes.get(tier,self.routes['instruct'])
        payload={
            'model':model,
            'messages':[{'role':'system','content':system},{'role':'user','content':user}],
            'temperature':temperature,'max_tokens':max_tokens,'stream':True,
            'stream_options':{'include_usage':True},
        }
        # Qwen3 style thinking is useful for planning/research/code but wastes latency on direct Q&A.
        if tier in {'reasoning','code'}: payload['chat_template_kwargs']={'enable_thinking':True}
        else: payload['chat_template_kwargs']={'enable_thinking':False}
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
            text=''.join(pieces).strip()
            if not text: text='I could not generate a response from the local model.'
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
        return Completion(text,route,model,latency*1000,ttft*1000 if ttft is not None else None,in_tok,out_tok,tps)

    async def complete(self,**kwargs)->str:
        return (await self.generate(**kwargs)).text

    async def json(self,*,system:str,user:str,tier:str='reasoning',fallback:dict[str,Any]|None=None,**kwargs)->dict[str,Any]:
        result=await self.generate(system=system+'\nReturn only valid JSON. No markdown fences.',user=user,tier=tier,temperature=.12,max_tokens=2600,**kwargs)
        try:
            m=re.search(r'\{.*\}',result.text,re.S); return json.loads(m.group(0) if m else result.text)
        except Exception:return fallback or {'raw':result.text}

router=ModelRouter()
