"""
opensquad/core/telemetry.py
Token usage, cost estimation, and execution latency metrics tracker for research evaluation.
"""

import time
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class TaskMetrics(BaseModel):
    task_id: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_sec: float = 0.0
    estimated_cost_usd: float = 0.0


class TelemetryTracker:
    """
    Tracks model tokens, latency, and costs across multi-agent pipeline executions.
    Default approximate cost calculation uses research benchmark standards:
    - Prompt tokens: $0.003 per 1K tokens
    - Completion tokens: $0.015 per 1K tokens
    """
    def __init__(self, prompt_token_rate: float = 0.003 / 1000, completion_token_rate: float = 0.015 / 1000):
        self.prompt_token_rate = prompt_token_rate
        self.completion_token_rate = completion_token_rate
        self.history: List[TaskMetrics] = []
        self._active_start_time: float = 0.0

    def start_timer(self):
        self._active_start_time = time.time()

    def stop_and_record(
        self,
        task_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> TaskMetrics:
        latency = round(time.time() - self._active_start_time, 3) if self._active_start_time > 0 else 0.0
        total_tokens = prompt_tokens + completion_tokens
        cost = round((prompt_tokens * self.prompt_token_rate) + (completion_tokens * self.completion_token_rate), 6)

        metric = TaskMetrics(
            task_id=task_id,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_sec=latency,
            estimated_cost_usd=cost
        )
        self.history.append(metric)
        self._active_start_time = 0.0
        return metric

    def get_aggregate_telemetry(self) -> Dict[str, Any]:
        total_tok = sum(m.total_tokens for m in self.history)
        total_cost = sum(m.estimated_cost_usd for m in self.history)
        total_time = sum(m.latency_sec for m in self.history)
        count = len(self.history)

        return {
            "execution_count": count,
            "total_tokens": total_tok,
            "total_cost_usd": round(total_cost, 6),
            "total_latency_sec": round(total_time, 3),
            "avg_tokens_per_task": round(total_tok / count, 2) if count > 0 else 0.0,
            "avg_latency_per_task": round(total_time / count, 3) if count > 0 else 0.0
        }
