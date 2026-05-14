"""
Benchmark Results Logger
=========================
Handles persistent logging of EVPC benchmark runs.
"""

import csv
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Directory where all benchmark runs are persisted
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "benchmark_results")


class ResultsLogger:
    """
    Persist and retrieve benchmark run results.

    Files:
      - benchmark_results/<timestamp>_results.csv  — per-sample rows
      - benchmark_results/<timestamp>_summary.json — aggregate metrics
    """

    def __init__(self) -> None:
        os.makedirs(RESULTS_DIR, exist_ok=True)

    def save(self, results: Dict[str, Any]) -> str:
        """
        Save a full benchmark results dict to disk.

        Args:
            results: Dict with "samples" and "summary" keys (from EVPCEngine).

        Returns:
            Path to the saved CSV file.
        """
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path  = os.path.join(RESULTS_DIR, f"{ts}_results.csv")
        json_path = os.path.join(RESULTS_DIR, f"{ts}_summary.json")

        samples = results.get("samples", [])
        summary = results.get("summary", {})

        # Write CSV
        if samples:
            fieldnames = list(samples[0].keys())
            try:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(samples)
                logger.info(f"Results CSV → {csv_path}")
            except OSError as exc:
                logger.error(f"Could not write CSV: {exc}")

        # Write JSON summary
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": ts, "summary": summary}, f, indent=2)
            logger.info(f"Summary JSON → {json_path}")
        except OSError as exc:
            logger.error(f"Could not write summary JSON: {exc}")

        return csv_path

    def load_latest(self) -> Dict[str, Any]:
        """
        Load the most recent benchmark run from disk.

        Returns:
            Dict with "samples" (list) and "summary" (dict), or empty dict on failure.
        """
        try:
            csv_files = sorted(
                [f for f in os.listdir(RESULTS_DIR) if f.endswith("_results.csv")]
            )
            if not csv_files:
                logger.warning("No saved benchmark results found.")
                return {}

            latest_csv = os.path.join(RESULTS_DIR, csv_files[-1])
            samples: List[Dict[str, Any]] = []

            with open(latest_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert boolean strings back
                    for bool_key in ("patch_generated", "evpc_verified", "false_fix"):
                        row[bool_key] = row.get(bool_key, "").lower() == "true"
                    samples.append(dict(row))

            # Try to load matching summary JSON
            ts_prefix = os.path.basename(latest_csv).replace("_results.csv", "")
            json_path = os.path.join(RESULTS_DIR, f"{ts_prefix}_summary.json")
            summary = {}
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    summary = data.get("summary", {})

            return {"samples": samples, "summary": summary}

        except Exception as exc:
            logger.error(f"Failed to load benchmark results: {exc}")
            return {}

    def list_runs(self) -> List[str]:
        """Return a list of all saved benchmark run timestamps."""
        try:
            return sorted(
                f.replace("_results.csv", "")
                for f in os.listdir(RESULTS_DIR)
                if f.endswith("_results.csv")
            )
        except OSError:
            return []
