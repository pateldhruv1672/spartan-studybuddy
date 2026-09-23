from __future__ import annotations

import hashlib, math
from typing import Iterable
import httpx
import numpy as np
from ..config import settings

class EmbeddingClient:
    def _fallback(self, text: str) -> np.ndarray:
        # Deterministic local fallback so ingestion remains functional before the embedding server starts.
        dim=settings.embedding_dim; vec=np.zeros(dim,dtype=np.float32)
        for tok in text.lower().split():
            h=hashlib.blake2b(tok.encode(),digest_size=16).digest()
            idx=int.from_bytes(h[:4],'little')%dim; sign=1.0 if h[4]&1 else -1.0
            vec[idx]+=sign*(1.0+math.log1p(len(tok)))
        n=float(np.linalg.norm(vec)); return vec/n if n else vec
    def embed(self, texts: list[str], query: bool=False) -> list[np.ndarray]:
        if not texts: return []
        inputs=[f'Instruct: Retrieve company code and documentation relevant to the engineering question.\nQuery: {t}' if query else t for t in texts]
        try:
            with httpx.Client(timeout=60) as client:
                r=client.post(settings.embedding_url.rstrip('/')+'/embeddings',headers={'Authorization':f'Bearer {settings.vllm_api_key}'},json={'model':settings.embedding_model,'input':inputs})
                r.raise_for_status(); data=sorted(r.json()['data'],key=lambda x:x['index'])
                out=[]
                for item in data:
                    v=np.asarray(item['embedding'],dtype=np.float32); n=np.linalg.norm(v); out.append(v/n if n else v)
                return out
        except Exception as exc:
            if settings.allow_embedding_fallback:
                return [self._fallback(t) for t in inputs]
            raise RuntimeError(
                'Embedding server is unavailable. StudyBuddy refuses to persist vectors from a different embedding space. '
                'Start the embedding model (make models) or set ALLOW_EMBEDDING_FALLBACK=1 only for tests/dev.'
            ) from exc
    def embed_batches(self, texts: list[str]) -> list[np.ndarray]:
        out=[]
        for i in range(0,len(texts),settings.embedding_batch): out.extend(self.embed(texts[i:i+settings.embedding_batch]))
        return out
embeddings=EmbeddingClient()

def pack(v: np.ndarray) -> bytes: return np.asarray(v,dtype=np.float32).tobytes()
def unpack(blob: bytes, dim: int) -> np.ndarray: return np.frombuffer(blob,dtype=np.float32,count=dim)
