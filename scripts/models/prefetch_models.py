#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess
from pathlib import Path
models=[os.getenv('SOCRATIC_BASE_MODEL','Qwen/Qwen3-32B'), os.getenv('EMBEDDING_MODEL','Qwen/Qwen3-Embedding-0.6B')]
if os.getenv('TRY_EAGLE3','1')=='1': models.append(os.getenv('EAGLE3_SPECULATOR_MODEL','RedHatAI/Qwen3-32B-speculator.eagle3'))
if os.getenv('PREFETCH_BROWSER_MODEL','0')=='1': models.append(os.getenv('DEDICATED_BROWSER_MODEL','browser-use/bu-30b-a3b-preview'))
extra=os.getenv('STUDYBUDDY_PREFETCH_EXTRA','').strip()
if extra: models.extend(x.strip() for x in extra.split(',') if x.strip())
models=list(dict.fromkeys(models)); runtime=os.getenv('VLLM_RUNTIME','docker')
if runtime=='docker':
    image=os.getenv('VLLM_IMAGE','vllm/vllm-openai:latest'); cache=Path(os.getenv('HF_HOME',str(Path.home()/'.cache/huggingface'))).expanduser(); cache.mkdir(parents=True,exist_ok=True); token=os.getenv('HF_TOKEN','')
    for model in models:
        print(f'\n==> Prefetching {model}',flush=True)
        code='from huggingface_hub import snapshot_download; print(snapshot_download(repo_id='+repr(model)+'))'
        subprocess.run(['docker','run','--rm','--entrypoint','','-e',f'HF_TOKEN={token}','-v',f'{cache}:/root/.cache/huggingface',image,'python3','-c',code],check=True)
else:
    from huggingface_hub import snapshot_download
    for model in models: print(snapshot_download(repo_id=model))
