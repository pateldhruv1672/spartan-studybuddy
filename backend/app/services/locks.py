"""Cross-process async coordination using transaction-scoped PostgreSQL locks."""
from contextlib import asynccontextmanager
import asyncio
import hashlib

from ..db import db


@asynccontextmanager
async def workflow_lock(key: str):
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
    with db() as conn:
        for _ in range(1200):
            if conn.execute('SELECT pg_try_advisory_xact_lock(?) AS acquired', (lock_id,)).fetchone()['acquired']:
                yield
                return
            await asyncio.sleep(0.1)
        raise TimeoutError('This operation is already running; retry shortly.')
