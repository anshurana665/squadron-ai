"""
OpenSquad AI — FastAPI Backend
REST + WebSocket API layer for the HTML/JS frontend.

Endpoints:
  POST /api/audit/file      → start single-file audit, returns job_id
  POST /api/audit/zip       → start ZIP audit, returns job_id
  WS   /ws/{job_id}         → stream live agent events for a job
  GET  /api/result/{job_id} → get final result after job completes
  GET  /health              → health check
"""
import os
import re
import logging
import time as _time
import uuid
import asyncio
import threading
import zipfile
import io
import json
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


# ─────────────────────────────────────────────────────────────
# TYPES
# ─────────────────────────────────────────────────────────────
class EventType(str, Enum):
    AGENT_START    = "agent_start"
    AGENT_THOUGHT  = "agent_thought"
    AGENT_DONE     = "agent_done"
    PATCH_READY    = "patch_ready"
    EVPC_RESULT    = "evpc_result"
    ERROR          = "error"
    COMPLETE       = "complete"


@dataclass
class AuditEvent:
    type:       str
    agent:      Optional[str]  = None
    message:    Optional[str]  = None
    data:       Optional[dict] = None
    timestamp:  str            = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if v is not None})


@dataclass
class AuditResult:
    job_id:          str
    success:         bool
    original_code:   str
    fixed_code:      Optional[str]   = None
    plan:            Optional[list]  = None
    vulnerabilities: Optional[list]  = None
    evpc_score:      Optional[float] = None
    test_output:     Optional[str]   = None
    error:           Optional[str]   = None
    changed:         bool            = False


# ─────────────────────────────────────────────────────────────
# IN-MEMORY JOB STORE
# Thread-safe: dict writes are GIL-protected for simple assignments.
# For production use Redis or a proper queue.
# ─────────────────────────────────────────────────────────────
_jobs: dict[str, AuditResult]         = {}
_job_events: dict[str, list[str]]     = {}   # job_id → list of serialized events
_job_done: dict[str, threading.Event] = {}   # job_id → Event signalling completion
_ws_queues: dict[str, asyncio.Queue]  = {}   # job_id → asyncio.Queue for live WS
_job_created: dict[str, float]        = {}   # job_id → monotonic timestamp

_JOB_TTL_SECONDS = 3600  # evict jobs older than 1 hour
_api_logger = logging.getLogger("opensquad.api")


def _evict_stale_jobs() -> None:
    """CWE-400 FIX: Remove jobs older than TTL to prevent memory exhaustion."""
    now = _time.monotonic()
    stale = [jid for jid, ts in _job_created.items() if now - ts > _JOB_TTL_SECONDS]
    for jid in stale:
        _jobs.pop(jid, None)
        _job_events.pop(jid, None)
        _job_done.pop(jid, None)
        _job_created.pop(jid, None)
        _ws_queues.pop(jid, None)


def _new_job(original_code: str) -> str:
    _evict_stale_jobs()
    job_id = str(uuid.uuid4())
    _jobs[job_id]       = AuditResult(job_id=job_id, success=False, original_code=original_code)
    _job_events[job_id] = []
    _job_done[job_id]   = threading.Event()
    _job_created[job_id] = _time.monotonic()
    return job_id


def _emit(job_id: str, event: AuditEvent) -> None:
    """Store event and push to any listening WebSocket queue."""
    serialized = event.to_json()
    _job_events[job_id].append(serialized)
    # Push to asyncio queue if a WS is connected
    q = _ws_queues.get(job_id)
    if q is not None:
        try:
            q.put_nowait(serialized)
        except asyncio.QueueFull:
            pass


def _finish_job(job_id: str, result: AuditResult) -> None:
    _jobs[job_id] = result
    _emit(job_id, AuditEvent(type=EventType.COMPLETE, data={"success": result.success}))
    _job_done[job_id].set()


# ─────────────────────────────────────────────────────────────
# AGENT RUNNER (runs in background thread — not async)
# ─────────────────────────────────────────────────────────────
def _run_agent_pipeline(
    job_id:        str,
    file_content:  str,
    filename:      str,
    issue_desc:    str,
    security_mode: bool,
) -> None:
    """
    Runs in a daemon thread. Emits AuditEvents and calls _finish_job().
    Pure function: reads only its arguments, writes only via _emit/_finish_job.
    """
    try:
        from opensquad.core.state import AgentState
        from opensquad.graph import app as agent_graph

        _emit(job_id, AuditEvent(
            type=EventType.AGENT_START,
            agent="manager",
            message="Manager is analysing the codebase...",
        ))

        state = AgentState(
            issue_description=issue_desc,
            repo_url="WEB_UPLOAD",
            plan=[],
            current_file=filename,
            file_content=file_content,
            security_mode=security_mode,
            generated_code=None,
            test_output=None,
            error=None,
            attempt_count=0,
            status="planning",
            messages=[],
            latest_thoughts=None,
            vulnerabilities=None,
            evpc_score=None,
            confidence=None,
            remaining_issues=None,
        )

        agent_states: dict[str, dict] = {}

        for output in agent_graph.stream(state):
            for node_name, node_state in output.items():
                # Per-agent tracking — no dict.update() collisions
                agent_states[node_name] = {
                    **(agent_states.get(node_name, {})),
                    **node_state,
                }

                thoughts = node_state.get("latest_thoughts", "")
                if thoughts and len(thoughts) > 10:
                    _emit(job_id, AuditEvent(
                        type=EventType.AGENT_THOUGHT,
                        agent=node_name,
                        message=thoughts[:600],
                    ))

                _emit(job_id, AuditEvent(
                    type=EventType.AGENT_DONE,
                    agent=node_name,
                    message=f"{node_name.capitalize()} completed.",
                ))

        # Extract typed results
        mgr = agent_states.get("manager",   {})
        dev = agent_states.get("developer", {})
        rev = agent_states.get("reviewer",  {})

        raw_fixed   = dev.get("generated_code") or ""
        fixed_code  = _clean_llm_output(raw_fixed) or file_content
        changed     = fixed_code.strip() != file_content.strip()
        evpc_score  = rev.get("evpc_score")

        _emit(job_id, AuditEvent(
            type=EventType.PATCH_READY,
            data={"changed": changed, "filename": filename},
        ))

        if evpc_score is not None:
            _emit(job_id, AuditEvent(
                type=EventType.EVPC_RESULT,
                data={"score": evpc_score},
            ))

        result = AuditResult(
            job_id=job_id,
            success=True,
            original_code=file_content,
            fixed_code=fixed_code,
            plan=mgr.get("plan"),
            vulnerabilities=mgr.get("vulnerabilities"),
            evpc_score=evpc_score,
            test_output=rev.get("test_output"),
            changed=changed,
        )
        _finish_job(job_id, result)

    except Exception as e:
        _api_logger.exception("Pipeline failed for job %s", job_id)
        _emit(job_id, AuditEvent(
            type=EventType.ERROR,
            message="An internal error occurred during analysis.",
        ))
        _finish_job(job_id, AuditResult(
            job_id=job_id,
            success=False,
            original_code=file_content,
            error="Internal pipeline error. Check server logs.",
        ))


def _clean_llm_output(raw: str) -> Optional[str]:
    """Strip markdown fences. Returns None if empty."""
    if not raw or not raw.strip():
        return None
    match = re.search(r"```(?:[a-zA-Z]+)?\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    result = match.group(1).strip() if match else raw.strip()
    return result if result else None


# ─────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────
MAX_FILE_BYTES    = 5 * 1024 * 1024
SUPPORTED_EXTS    = frozenset(["py", "js", "html", "css", "cpp", "java"])

def _validate_file(filename: str, content: bytes) -> str:
    """Raises ValueError on invalid input. Returns decoded text."""
    if len(content) == 0:
        raise ValueError(f"'{filename}' is empty.")
    if len(content) > MAX_FILE_BYTES:
        mb = len(content) / (1024 * 1024)
        raise ValueError(f"'{filename}' is {mb:.1f} MB — max 5 MB.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported file type '.{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTS))}")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"'{filename}' is not valid UTF-8.")


# ─────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="OpenSquad AI API", version="4.0")

# CWE-693 FIX: restrict CORS to known origins
_ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5000,http://localhost:8501,http://localhost:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0"}


@app.post("/api/audit/file")
async def audit_file(
    file:          UploadFile = File(...),
    issue_desc:    str        = Form("Analyze for bugs and security vulnerabilities. Fix all issues."),
    security_mode: bool       = Form(False),
):
    """
    Start a single-file audit job.
    Returns job_id immediately — client connects to /ws/{job_id} for live progress.
    """
    raw = await file.read()

    try:
        text = _validate_file(file.filename, raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    job_id = _new_job(original_code=text)

    # Run in background thread — agent pipeline is blocking I/O
    t = threading.Thread(
        target=_run_agent_pipeline,
        args=(job_id, text, file.filename, issue_desc, security_mode),
        daemon=True,
        name=f"audit-{job_id[:8]}",
    )
    t.start()

    return {"job_id": job_id, "filename": file.filename, "status": "started"}


@app.post("/api/audit/zip")
async def audit_zip(
    file:          UploadFile = File(...),
    security_mode: bool       = Form(False),
):
    """
    Start a ZIP codebase audit.
    Extracts all supported files and audits them sequentially (streaming per file).
    Returns job_id for WebSocket connection.
    """
    raw = await file.read()

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="Invalid ZIP file.")

    file_pairs: list[tuple[str, str]] = []
    for name in zf.namelist():
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in SUPPORTED_EXTS:
            try:
                code = zf.read(name).decode("utf-8")
                file_pairs.append((code, name))
            except (UnicodeDecodeError, KeyError):
                pass

    if not file_pairs:
        raise HTTPException(status_code=422, detail="No supported code files found in ZIP.")

    # Use first file as "representative" for job creation
    job_id = _new_job(original_code=file_pairs[0][0])

    def _run_zip():
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="zip-worker") as executor:
            future_map = {
                executor.submit(
                    _run_agent_pipeline,
                    f"{job_id}-{i}", code, fname,
                    "Full codebase audit. Fix bugs and security issues.",
                    security_mode,
                ): fname
                for i, (code, fname) in enumerate(file_pairs)
            }
            for future in as_completed(future_map):
                fname = future_map[future]
                try:
                    future.result()
                    results.append(fname)
                    _emit(job_id, AuditEvent(
                        type=EventType.AGENT_DONE,
                        agent="batch",
                        message=f"Patched: {fname}",
                    ))
                except Exception as e:
                    _emit(job_id, AuditEvent(
                        type=EventType.ERROR,
                        message=f"Failed {fname}: {e}",
                    ))

        _finish_job(job_id, AuditResult(
            job_id=job_id,
            success=True,
            original_code="",
            fixed_code=None,
            changed=len(results) > 0,
        ))

    t = threading.Thread(target=_run_zip, daemon=True, name=f"zip-{job_id[:8]}")
    t.start()

    return {
        "job_id":     job_id,
        "file_count": len(file_pairs),
        "status":     "started",
    }


@app.get("/api/result/{job_id}")
def get_result(job_id: str):
    """
    Get the final result of a completed audit job.
    Poll this after WebSocket closes or after receiving 'complete' event.
    """
    result = _jobs.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {
        "job_id":          result.job_id,
        "success":         result.success,
        "changed":         result.changed,
        "original_code":   result.original_code,
        "fixed_code":      result.fixed_code,
        "plan":            result.plan,
        "vulnerabilities": result.vulnerabilities,
        "evpc_score":      result.evpc_score,
        "test_output":     result.test_output,
        "error":           result.error,
    }


@app.websocket("/ws/{job_id}")
async def websocket_stream(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for live agent progress streaming.
    Sends all buffered events (for late connects) then streams new ones.
    Closes automatically when the job completes.
    """
    await websocket.accept()

    if job_id not in _jobs:
        await websocket.send_text(AuditEvent(
            type=EventType.ERROR, message="Job not found."
        ).to_json())
        await websocket.close()
        return

    # Create asyncio queue for this connection
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _ws_queues[job_id] = q

    # Replay any events that happened before WS connected
    for past_event in _job_events.get(job_id, []):
        await websocket.send_text(past_event)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                await websocket.send_text(msg)
                # If this is the complete event, close gracefully
                if '"type": "complete"' in msg or '"type":"complete"' in msg:
                    break
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text('{"type":"ping"}')

    except WebSocketDisconnect:
        pass
    finally:
        _ws_queues.pop(job_id, None)
        await websocket.close()


# ─────────────────────────────────────────────────────────────
# SERVE STATIC FILES
# ─────────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
