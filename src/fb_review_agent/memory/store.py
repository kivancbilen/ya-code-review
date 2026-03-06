"""F3: Known pattern store — JSON-backed persistence for learned review patterns."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class KnownPattern:
    """A learned code review pattern to check for in future reviews."""

    id: str  # e.g. "P001"
    pattern: str  # short description
    description: str  # detailed explanation
    severity: str  # default severity (critical/high/medium/low)
    category: str  # correctness/security/performance/etc
    file_patterns: list[str] = field(default_factory=list)  # glob patterns
    example_snippet: str = ""
    created_at: str = ""
    hit_count: int = 0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


DEFAULT_MEMORY_PATH = Path.home() / ".fb-review" / "memory.json"


class PatternStore:
    """JSON-backed store for known review patterns."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_MEMORY_PATH
        self._patterns: list[KnownPattern] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._patterns = [KnownPattern(**p) for p in data.get("patterns", [])]
            except (json.JSONDecodeError, TypeError):
                self._patterns = []
        else:
            self._patterns = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"patterns": [asdict(p) for p in self._patterns]}
        self.path.write_text(json.dumps(data, indent=2))

    def _next_id(self) -> str:
        if not self._patterns:
            return "P001"
        max_num = max(int(p.id[1:]) for p in self._patterns if p.id.startswith("P") and p.id[1:].isdigit())
        return f"P{max_num + 1:03d}"

    def add(self, pattern: KnownPattern) -> None:
        if not pattern.id:
            pattern.id = self._next_id()
        self._patterns.append(pattern)
        self._save()

    def remove(self, pattern_id: str) -> bool:
        before = len(self._patterns)
        self._patterns = [p for p in self._patterns if p.id != pattern_id]
        if len(self._patterns) < before:
            self._save()
            return True
        return False

    def list_all(self) -> list[KnownPattern]:
        return list(self._patterns)

    def find_relevant(self, files: list[str]) -> list[KnownPattern]:
        """Find patterns whose file_patterns match any of the given files."""
        matched: list[KnownPattern] = []
        for p in self._patterns:
            if not p.file_patterns:
                # Patterns with no file filter always match
                matched.append(p)
                continue
            for fp in p.file_patterns:
                if any(fnmatch.fnmatch(f, fp) for f in files):
                    matched.append(p)
                    break
        return matched

    def record_hit(self, pattern_id: str) -> None:
        for p in self._patterns:
            if p.id == pattern_id:
                p.hit_count += 1
                self._save()
                return

    def export_json(self) -> str:
        return json.dumps({"patterns": [asdict(p) for p in self._patterns]}, indent=2)

    def import_json(self, json_text: str) -> int:
        """Import patterns from JSON text. Returns count of imported patterns."""
        data = json.loads(json_text)
        imported = 0
        existing_ids = {p.id for p in self._patterns}
        for p_data in data.get("patterns", []):
            pattern = KnownPattern(**p_data)
            if pattern.id not in existing_ids:
                self._patterns.append(pattern)
                existing_ids.add(pattern.id)
                imported += 1
        if imported:
            self._save()
        return imported


def format_patterns_for_template(patterns: list[KnownPattern]) -> str:
    """Format matched patterns as a checklist section for the review template."""
    if not patterns:
        return ""
    lines = ["## Known Patterns to Check\n"]
    lines.append("The following known patterns are relevant to the files being reviewed.")
    lines.append("Check each one during your analysis:\n")
    for p in patterns:
        lines.append(f"- [ ] **{p.id}: {p.pattern}** [{p.severity}] ({p.category})")
        lines.append(f"  {p.description}")
        if p.example_snippet:
            lines.append(f"  ```\n  {p.example_snippet}\n  ```")
        lines.append("")
    return "\n".join(lines)
