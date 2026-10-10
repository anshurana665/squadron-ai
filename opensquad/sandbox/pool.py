"""
opensquad/sandbox/pool.py
Pre-allocated warm container pool manager to reduce spin-up latency during large-scale evaluation.
"""

import asyncio
from pathlib import Path
from typing import Optional, List
from opensquad.sandbox.e2b_executor import HardenedE2BExecutor


class ContainerPoolManager:
    """
    Manages a pool of pre-allocated warm sandbox containers ready for immediate code execution.
    """
    def __init__(self, workspace_root: Optional[Path] = None, pool_size: int = 3, timeout_sec: int = 10):
        self.workspace_root = workspace_root
        self.pool_size = pool_size
        self.timeout_sec = timeout_sec
        self._pool: List[HardenedE2BExecutor] = []
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Pre-allocates warm container executors."""
        async with self._lock:
            if self._initialized:
                return
            for _ in range(self.pool_size):
                executor = HardenedE2BExecutor(
                    workspace_root=self.workspace_root,
                    timeout_sec=self.timeout_sec
                )
                executor.start()
                self._pool.append(executor)
            self._initialized = True

    async def acquire_container(self) -> HardenedE2BExecutor:
        """Retrieves an available executor from the warm pool, or creates a new one if exhausted."""
        async with self._lock:
            if not self._initialized and self.pool_size > 0:
                # Synchronous fallback init for fast startup if initialize wasn't explicitly called
                pass
            if self._pool:
                return self._pool.pop()
            
        # If pool empty, instantiate on demand
        executor = HardenedE2BExecutor(workspace_root=self.workspace_root, timeout_sec=self.timeout_sec)
        executor.start()
        return executor

    async def release_container(self, executor: HardenedE2BExecutor):
        """Returns a container to the warm pool if within capacity, otherwise closes it."""
        async with self._lock:
            if len(self._pool) < self.pool_size and executor.is_active:
                self._pool.append(executor)
            else:
                executor.close()

    async def shutdown(self):
        """Closes all warm container instances in the pool."""
        async with self._lock:
            while self._pool:
                ex = self._pool.pop()
                ex.close()
            self._initialized = False
