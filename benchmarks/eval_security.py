"""
benchmarks/eval_security.py
Evaluates Squadron.AI on cases from the Hugging Face s2e-lab/SecurityEval dataset one-by-one.
"""

import urllib.request
import json
import time
import sys
import concurrent.futures
import threading
from pathlib import Path

from opensquad.core.graph import app
from opensquad.core.state import AgentState
from opensquad.agents.manager import classify_vulnerabilities

BENCHMARK_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCHMARK_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def fetch_security_eval_cases(limit=3):
    cache_file = DATA_DIR / "security_eval_cache.json"
    if cache_file.exists():
        try:
            cached_rows = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached_rows, list) and len(cached_rows) >= limit:
                print(f"[+] Loaded {len(cached_rows)} dataset cases from local cache. Slicing to limit={limit}.")
                return cached_rows[:limit]
        except Exception as e:
            print(f"[!] Failed reading cache ({e}), re-fetching...")

    # Fetch 100 cases once and cache them locally so network timeouts never happen again
    fetch_len = max(limit, 100)
    url = f"https://datasets-server.huggingface.co/rows?dataset=s2e-lab/SecurityEval&config=default&split=train&offset=0&limit={fetch_len}"
    print(f"[*] Fetching {fetch_len} cases from s2e-lab/SecurityEval via Hugging Face API...")

    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Squadron.AI Evaluator)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = [r.get("row", r) for r in data.get("rows", [])]
                print(f"[+] Successfully loaded {len(rows)} dataset rows from HF API.")
                try:
                    cache_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")
                    print(f"[+] Cached dataset to {cache_file}")
                except Exception as ce:
                    print(f"[!] Cache save failed: {ce}")
                return rows[:limit]
        except Exception as e:
            print(f"[-] Attempt {attempt}/3 error fetching from HF server: {e}", flush=True)
            if attempt < 3:
                time.sleep(2 * attempt)
    print("[-] Could not retrieve dataset cases after 3 attempts.")
    return []


def evaluate_case(case_idx: int, case_data: dict):
    print("\n" + "=" * 70)
    case_id = case_data.get("ID", case_data.get("id", f"case_{case_idx+1}"))
    prompt_text = case_data.get("Prompt", case_data.get("prompt", ""))
    insecure_code = case_data.get("Insecure_code", case_data.get("insecure_code", case_data.get("code", "")))
    cwe_label = case_data.get("CWE", case_data.get("cwe", case_data.get("cwe_id", "Unknown-CWE")))

    print(f"[*] EVALUATING CASE #{case_idx+1} | ID: {case_id} | CWE Target: {cwe_label}")
    print(f"    Prompt Preview: {prompt_text[:120].strip()}...")
    print(f"    Insecure Snippet LOC: {len(insecure_code.splitlines())}")

    # Step 1: Pre-audit SAST check
    initial_vulns = classify_vulnerabilities(insecure_code)
    print(f"[1] SAST Pre-Scan: Detected {len(initial_vulns)} vulnerabilities: {[v.get('cwe_id') for v in initial_vulns]}")

    # Step 2: Initialize Agent State
    state = AgentState(
        issue_description=f"Fix vulnerability {cwe_label}: {prompt_text}",
        repo_url="SecurityEval_Dataset",
        plan=[],
        current_file=f"{case_id}.py",
        file_content=insecure_code,
        security_mode=True,
        generated_code=None,
        test_output=None,
        error=None,
        attempt_count=0,
        status="planning",
        messages=[],
        latest_thoughts=None,
        vulnerabilities=initial_vulns,
        evpc_score=None,
        confidence=None,
        remaining_issues=None,
    )

    # Step 3: Run OpenSquad State Machine
    t0 = time.time()
    final_state = state
    try:
        print("[2] Dispatching to Agent Graph (Manager -> Red-Team -> Developer -> Reviewer)...")
        for chunk in app.stream(state):
            for node, s in chunk.items():
                print(f"    --> [{node.upper()}] Status: {s.get('status')} | Attempt: {s.get('attempt_count', 0)}")
                if s.get("latest_thoughts"):
                    thought_preview = s['latest_thoughts'][:100].replace('\n', ' ')
                    print(f"        Thought: {thought_preview}...")
                final_state = {**final_state, **s}
    except Exception as e:
        print(f"[!] Pipeline Execution Error on Case {case_id}: {e}")
        return None

    elapsed = round(time.time() - t0, 2)
    evpc = final_state.get("evpc_score", 0.0)
    status = final_state.get("status", "unknown")
    patched_code = final_state.get("generated_code") or ""

    # Step 4: Post-audit verification
    post_vulns = classify_vulnerabilities(patched_code) if patched_code else []
    print(f"[3] Result Summary for Case {case_id}:")
    print(f"    Status: {status} in {elapsed}s")
    print(f"    EVPC Verification Score: {evpc}")
    print(f"    Pre-patch Vulns: {len(initial_vulns)} -> Post-patch Vulns: {len(post_vulns)}")

    return {
        "case_idx": case_idx + 1,
        "case_id": case_id,
        "target_cwe": cwe_label,
        "time_seconds": elapsed,
        "final_status": status,
        "evpc_score": evpc,
        "pre_vuln_count": len(initial_vulns),
        "post_vuln_count": len(post_vulns),
        "patched_code": patched_code,
        "original_code": insecure_code,
    }


def main():
    limit = 3
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])

    cases = fetch_security_eval_cases(limit=limit)
    if not cases:
        print("[-] Could not retrieve dataset cases from Hugging Face.", flush=True)
        return

    out_file = DATA_DIR / "security_eval_results_claude_opus.json"
    results = []
    completed_indices = set()

    # Load previously completed cases if file exists to avoid duplicating cost and time
    if out_file.exists():
        try:
            existing_data = json.loads(out_file.read_text(encoding="utf-8"))
            if isinstance(existing_data, list):
                results = existing_data
                completed_indices = {r.get("case_idx") for r in results if r.get("final_status") == "done"}
                print(f"[*] Loaded {len(results)} existing results from {out_file}. (Completed indices: {sorted(list(completed_indices))})", flush=True)
        except Exception as e:
            print(f"[!] Could not read existing results file: {e}", flush=True)

    print(f"\n[*] Starting evaluation on up to {len(cases)} cases...", flush=True)

    file_lock = threading.Lock()

    def process_case(idx, c):
        case_num = idx + 1
        if case_num in completed_indices:
            print(f"\n[i] Skipping Case {case_num} (already evaluated and stored).", flush=True)
            return

        res = evaluate_case(idx, c)
        if res:
            with file_lock:
                existing_idx = next((i for i, r in enumerate(results) if r.get("case_idx") == case_num), None)
                if existing_idx is not None:
                    results[existing_idx] = res
                else:
                    results.append(res)

                # Save progressively after every case
                out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
                print(f"    [+] Saved updated results (Total completed: {len(results)}) to {out_file.name}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = [executor.submit(process_case, idx, c) for idx, c in enumerate(cases)]
        concurrent.futures.wait(futures)

    print("\n" + "=" * 70, flush=True)
    print(f"[+] One-by-one dataset evaluation completed! All results preserved in {out_file}", flush=True)


if __name__ == "__main__":
    main()
