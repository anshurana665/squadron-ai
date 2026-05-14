"""
opensquad/benchmark/evpc_engine.py
EVPC (Execution-Verified Patch Confidence) Benchmark Engine.
Core evaluation module for the research paper.
Runs OpenSquad pipeline on a dataset of known vulnerabilities
and measures: patch rate, EVPC score, false-fix rate, latency.
"""
import time
import json
import csv
import os
from datetime import datetime
from opensquad.core.state import AgentState


class EVPCEngine:
    """
    Runs the full OpenSquad agent pipeline against a vulnerability dataset
    and produces research-paper-ready metrics.
    """

    def __init__(self):
        # Lazy import to avoid circular dependency
        from opensquad.graph import app as agent_graph
        self.graph = agent_graph

    # ── Main benchmark runner ────────────────────────────────────────
    def run_benchmark(self, dataset: list[dict], security_mode: bool = True) -> dict:
        """
        Args:
            dataset : list of vulnerability dicts from dataset_loader.DATASET
            security_mode : run agents in security audit mode

        Returns:
            {
              "summary": { ... },
              "results": [ per-file result dicts ],
            }
        """
        results    = []
        start_all  = time.time()

        for item in dataset:
            result = self._run_single(item, security_mode)
            results.append(result)

        total_time = round(time.time() - start_all, 2)
        summary    = self._compute_summary(results, total_time)

        return {"summary": summary, "results": results}

    # ── Single file run ──────────────────────────────────────────────
    def _run_single(self, item: dict, security_mode: bool) -> dict:
        filename   = item["filename"]
        vuln_code  = item["vulnerable_code"]
        cwe_id     = item.get("cwe_id", "UNKNOWN")
        vuln_type  = item.get("vulnerability_type", "Unknown")
        expected   = item.get("expected_fix_pattern", "")

        record = {
            "filename":          filename,
            "vulnerability_type": vuln_type,
            "cwe_id":            cwe_id,
            "severity":          item.get("severity", "UNKNOWN"),
            "cvss_score":        item.get("cvss_score", 0.0),
            "patch_generated":   False,
            "evpc_verified":     False,
            "evpc_score":        None,
            "false_fix":         False,
            "detection_correct": False,
            "time_seconds":      0.0,
            "error":             None,
        }

        start = time.time()
        try:
            state = AgentState(
                issue_description = f"Security audit: fix {vuln_type} ({cwe_id})",
                repo_url          = "BENCHMARK",
                plan              = [],
                current_file      = filename,
                file_content      = vuln_code,
                security_mode     = security_mode,
                generated_code    = None,
                test_output       = None,
                error             = None,
                attempt_count     = 0,
                status            = "planning",
                messages          = [],
                latest_thoughts   = None,
                vulnerabilities   = None,
                evpc_score        = None,
            )

            final = self.graph.invoke(state)

            patched    = final.get("generated_code") or ""
            evpc_score = final.get("evpc_score")
            vulns      = final.get("vulnerabilities") or []

            # Patch generated?
            patch_generated = bool(patched and patched.strip() != vuln_code.strip())
            record["patch_generated"] = patch_generated

            # EVPC verified?
            record["evpc_score"]    = evpc_score
            record["evpc_verified"] = (evpc_score == 1.0)

            # False fix: patch generated but broke something (evpc_score=0)
            record["false_fix"] = patch_generated and (evpc_score == 0.0)

            # Detection correct: did manager find the right CWE?
            detected_cwes = [v.get("cwe_id", "") for v in vulns]
            record["detection_correct"] = cwe_id in detected_cwes

            # Validate fix quality if expected pattern given
            if expected and patched:
                record["fix_quality"] = expected.lower() in patched.lower()
            else:
                record["fix_quality"] = None

        except Exception as e:
            record["error"] = str(e)[:300]

        record["time_seconds"] = round(time.time() - start, 2)
        return record

    # ── Metrics computation ──────────────────────────────────────────
    def calculate_evpc_score(self, results: list[dict]) -> float:
        """
        Calculates the aggregate EVPC score from a list of results.
        Raises ValueError if results is empty.
        """
        n = len(results)
        if n == 0:
            raise ValueError("Cannot calculate EVPC score for empty results list.")
        verified_count = sum(1 for r in results if r.get("evpc_verified", False))
        return round(verified_count / n, 3)

    def _compute_summary(self, results: list[dict], total_time: float) -> dict:
        n = len(results)
        if n == 0:
            return {}

        patched        = [r for r in results if r["patch_generated"]]
        verified       = [r for r in results if r["evpc_verified"]]
        false_fixes    = [r for r in results if r["false_fix"]]
        detected_right = [r for r in results if r["detection_correct"]]
        times          = [r["time_seconds"] for r in results]

        return {
            "total_files":                n,
            "patch_generation_rate":      round(len(patched) / n, 3),
            "evpc_score_avg":             round(
                sum(r["evpc_score"] or 0 for r in results) / n, 3
            ),
            "evpc_verified_rate":         round(len(verified) / n, 3),
            "false_fix_rate":             round(len(false_fixes) / n, 3),
            "detection_accuracy":         round(len(detected_right) / n, 3),
            "avg_time_per_file_seconds":  round(sum(times) / n, 2),
            "total_time_seconds":         total_time,
            "timestamp":                  datetime.now().isoformat(),
        }

    # ── Save to CSV ──────────────────────────────────────────────────
    def save_results(self, benchmark_output: dict, output_dir: str = "/tmp") -> str:
        """Save full results to CSV. Returns file path."""
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(output_dir, f"evpc_results_{ts}.csv")

        results = benchmark_output.get("results", [])
        if not results:
            return ""

        keys = list(results[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

        # Also save summary JSON
        summary_path = path.replace(".csv", "_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(benchmark_output.get("summary", {}), f, indent=2)

        return path
