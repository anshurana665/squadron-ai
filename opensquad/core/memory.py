"""
opensquad/core/memory.py
Vector/JSON experience replay store for pattern persistence across repairs.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class PatchPattern(BaseModel):
    pattern_id: str
    cwe_id: str
    vulnerability_snippet: str
    fix_snippet: str
    success_rate: float = 1.0
    tags: List[str] = []


class ExperienceStore:
    """
    Persists successful repair patterns and syntax solutions in JSON/memory storage
    to allow multi-case learning and pattern recall during patching.
    """
    def __init__(self, store_path: Optional[Path] = None):
        if store_path:
            self.store_file = store_path.resolve()
        else:
            self.store_file = Path("workspace/experience_store.json")
        self.patterns: Dict[str, PatchPattern] = {}
        self._load_store()

    def _load_store(self):
        if self.store_file.exists():
            try:
                data = json.loads(self.store_file.read_text(encoding="utf-8"))
                for key, val in data.items():
                    self.patterns[key] = PatchPattern(**val)
            except Exception:
                self.patterns = {}

    def _save_store(self):
        try:
            self.store_file.parent.mkdir(parents=True, exist_ok=True)
            export_data = {k: v.model_dump() for k, v in self.patterns.items()}
            self.store_file.write_text(json.dumps(export_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def record_pattern(self, pattern_id: str, cwe_id: str, vuln_snippet: str, fix_snippet: str, tags: Optional[List[str]] = None):
        pattern = PatchPattern(
            pattern_id=pattern_id,
            cwe_id=cwe_id,
            vulnerability_snippet=vuln_snippet,
            fix_snippet=fix_snippet,
            tags=tags or []
        )
        self.patterns[pattern_id] = pattern
        self._save_store()

    def query_patterns(self, cwe_id: str, limit: int = 3) -> List[PatchPattern]:
        """Retrieves past successful fix patterns matching the target CWE or keywords."""
        matches = [p for p in self.patterns.values() if p.cwe_id.lower() == cwe_id.lower()]
        return sorted(matches, key=lambda x: x.success_rate, reverse=True)[:limit]
