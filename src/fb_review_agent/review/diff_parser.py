"""Parse git unified diffs into structured models."""

from __future__ import annotations

from dataclasses import dataclass, field

import unidiff


@dataclass
class DiffHunk:
    """A single hunk within a file diff."""

    source_start: int
    source_length: int
    target_start: int
    target_length: int
    content: str


@dataclass
class FileDiff:
    """Diff information for a single file."""

    source_file: str
    target_file: str
    is_new: bool = False
    is_deleted: bool = False
    is_rename: bool = False
    hunks: list[DiffHunk] = field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0

    @property
    def path(self) -> str:
        """The most relevant file path (target for modifications, source for deletions)."""
        if self.is_deleted:
            return self.source_file
        return self.target_file


@dataclass
class ParsedDiff:
    """Complete parsed diff with all file changes."""

    files: list[FileDiff] = field(default_factory=list)
    raw_diff: str = ""

    @property
    def total_added(self) -> int:
        return sum(f.added_lines for f in self.files)

    @property
    def total_removed(self) -> int:
        return sum(f.removed_lines for f in self.files)

    @property
    def changed_files(self) -> list[str]:
        return [f.path for f in self.files]

    def summary(self) -> str:
        lines = [f"{len(self.files)} files changed, +{self.total_added} -{self.total_removed}"]
        for f in self.files:
            status = ""
            if f.is_new:
                status = " (new)"
            elif f.is_deleted:
                status = " (deleted)"
            elif f.is_rename:
                status = f" (renamed from {f.source_file})"
            lines.append(f"  {f.path}{status}: +{f.added_lines} -{f.removed_lines}")
        return "\n".join(lines)


def parse_diff(diff_text: str) -> ParsedDiff:
    """Parse a unified diff string into structured data."""
    if not diff_text.strip():
        return ParsedDiff(raw_diff=diff_text)

    try:
        patch_set = unidiff.PatchSet.from_string(diff_text)
    except Exception:
        # Fall back to returning raw diff if parsing fails
        return ParsedDiff(raw_diff=diff_text)

    files = []
    for patched_file in patch_set:
        source = patched_file.source_file
        target = patched_file.target_file

        # Strip a/ b/ prefixes
        if source.startswith("a/"):
            source = source[2:]
        if target.startswith("b/"):
            target = target[2:]

        hunks = []
        for hunk in patched_file:
            hunk_lines = []
            for line in hunk:
                hunk_lines.append(str(line))
            hunks.append(DiffHunk(
                source_start=hunk.source_start,
                source_length=hunk.source_length,
                target_start=hunk.target_start,
                target_length=hunk.target_length,
                content="".join(hunk_lines),
            ))

        files.append(FileDiff(
            source_file=source,
            target_file=target,
            is_new=patched_file.is_added_file,
            is_deleted=patched_file.is_removed_file,
            is_rename=source != target and not patched_file.is_added_file and not patched_file.is_removed_file,
            hunks=hunks,
            added_lines=patched_file.added,
            removed_lines=patched_file.removed,
        ))

    return ParsedDiff(files=files, raw_diff=diff_text)
