"""F7: Test coverage analysis — static analysis of which changed code has test coverage."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from fb_review_agent.review.diff_parser import FileDiff


@dataclass
class ChangedSymbol:
    """A function/class extracted from diff hunks."""

    file: str
    name: str
    line_start: int
    line_end: int


@dataclass
class TestMapping:
    """Mapping from a changed symbol to its test files."""

    symbol: ChangedSymbol
    test_files: list[str] = field(default_factory=list)
    confidence: str = "none"  # high/medium/low/none


@dataclass
class CoverageReport:
    """Result of test coverage analysis."""

    mappings: list[TestMapping] = field(default_factory=list)
    uncovered_symbols: list[ChangedSymbol] = field(default_factory=list)
    coverage_ratio: float = 0.0


# Regex patterns for extracting symbol definitions from diff hunks
SYMBOL_PATTERNS = [
    # Python: def function_name( or class ClassName
    re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^\+\s*class\s+(\w+)", re.MULTILINE),
    # JavaScript/TypeScript: function name(, const name =, class Name
    re.compile(r"^\+\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^\+\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function)", re.MULTILINE),
    re.compile(r"^\+\s*(?:export\s+)?class\s+(\w+)", re.MULTILINE),
    # TS/JS method definitions: public/private/protected/static/async methodName(
    re.compile(r"^\+\s+(?:public|private|protected|static|readonly|\s)*(?:async\s+)?([a-zA-Z_]\w+)\s*\([^)]*\)\s*(?::\s*\S+)?\s*\{", re.MULTILINE),
    # TS arrow functions assigned to properties: propertyName = (...) =>
    re.compile(r"^\+\s+(?:public|private|protected|static|readonly|\s)*([a-zA-Z_]\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>", re.MULTILINE),
    # TS interface/type: export interface Name / export type Name
    re.compile(r"^\+\s*(?:export\s+)?(?:interface|type)\s+(\w+)", re.MULTILINE),
]

# Test file naming conventions
TEST_PATTERNS = [
    "test_{name}.py",
    "{name}_test.py",
    "tests/test_{name}.py",
    "tests/{name}_test.py",
    "{name}.test.ts",
    "{name}.test.tsx",
    "{name}.test.js",
    "{name}.test.jsx",
    "{name}.spec.ts",
    "{name}.spec.tsx",
    "{name}.spec.js",
    "__tests__/{name}.tsx",
    "__tests__/{name}.ts",
    "__tests__/{name}.test.tsx",
    "__tests__/{name}.test.ts",
]


def _extract_symbols_from_hunk(file_path: str, hunk_content: str, target_start: int) -> list[ChangedSymbol]:
    """Extract function/class names from added lines in a diff hunk."""
    symbols: list[ChangedSymbol] = []
    seen_names: set[str] = set()

    for pattern in SYMBOL_PATTERNS:
        for match in pattern.finditer(hunk_content):
            name = match.group(1)
            # Skip control flow keywords and common false positives
            if name in (
                "if", "else", "for", "while", "switch", "return", "throw",
                "try", "catch", "finally", "do", "with", "yield", "await",
                "__init__", "__str__", "__repr__", "constructor", "render", "toString",
            ):
                continue
            if name in seen_names:
                continue
            seen_names.add(name)

            # Estimate line number from match position
            line_offset = hunk_content[:match.start()].count("\n")
            symbols.append(ChangedSymbol(
                file=file_path,
                name=name,
                line_start=target_start + line_offset,
                line_end=target_start + line_offset + 5,  # approximate
            ))

    return symbols


def _find_test_files_by_convention(file_path: str, repo_root: str) -> list[str]:
    """Find test files by naming convention for a given source file."""
    p = Path(file_path)
    stem = p.stem  # e.g. "orchestrator" from "orchestrator.py"
    parent = p.parent

    found: list[str] = []
    for pattern in TEST_PATTERNS:
        test_name = pattern.format(name=stem)
        # Try relative to file's directory
        candidate = parent / test_name
        full_path = Path(repo_root) / candidate
        if full_path.exists():
            found.append(str(candidate))
        # Try relative to repo root
        full_path = Path(repo_root) / test_name
        if full_path.exists():
            found.append(test_name)

    return list(set(found))


def _grep_for_symbol(symbol_name: str, test_files: list[str], repo_root: str) -> list[str]:
    """Grep test files for references to a symbol. Returns files that reference it."""
    if not test_files:
        return []

    matching: list[str] = []
    for tf in test_files:
        full_path = Path(repo_root) / tf
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text()
            if symbol_name in content:
                matching.append(tf)
        except (OSError, UnicodeDecodeError):
            continue

    return matching


def _search_test_dirs(symbol_name: str, repo_root: str) -> list[str]:
    """Search common test directories for references to a symbol."""
    test_dirs = ["tests", "test", "__tests__", "spec"]
    found: list[str] = []

    for td in test_dirs:
        test_dir = Path(repo_root) / td
        if not test_dir.is_dir():
            continue
        try:
            result = subprocess.run(
                ["grep", "-rl", "--color=never", symbol_name, str(test_dir)],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    rel = os.path.relpath(line.strip(), repo_root)
                    found.append(rel)
        except (subprocess.TimeoutExpired, OSError):
            continue

    return found


def analyze_coverage(
    files: list[FileDiff],
    repo_root: str,
) -> CoverageReport:
    """Analyze test coverage for changed symbols using static analysis.

    1. Extract changed function/class names from diff hunks
    2. Search for test files by naming convention
    3. Grep test files for references to changed symbols
    4. Classify coverage confidence: high/medium/low/none
    """
    all_symbols: list[ChangedSymbol] = []

    # Step 1: Extract symbols from diffs
    for f in files:
        if f.is_deleted:
            continue
        for hunk in f.hunks:
            symbols = _extract_symbols_from_hunk(f.path, hunk.content, hunk.target_start)
            all_symbols.extend(symbols)

    if not all_symbols:
        return CoverageReport()

    mappings: list[TestMapping] = []
    uncovered: list[ChangedSymbol] = []

    for sym in all_symbols:
        # Step 2: Find test files by convention
        convention_tests = _find_test_files_by_convention(sym.file, repo_root)

        # Step 3: Grep for symbol references in test files
        direct_refs = _grep_for_symbol(sym.name, convention_tests, repo_root)

        # Also search test directories broadly
        broad_refs = _search_test_dirs(sym.name, repo_root)

        all_test_files = list(set(direct_refs + broad_refs))
        convention_only = [t for t in convention_tests if t not in direct_refs]

        # Step 4: Classify confidence
        if direct_refs:
            confidence = "high"  # direct import + reference in test file
        elif broad_refs:
            confidence = "medium"  # found in some test file
        elif convention_tests:
            confidence = "low"  # test file exists but doesn't reference symbol
        else:
            confidence = "none"

        mapping = TestMapping(
            symbol=sym,
            test_files=all_test_files or convention_only,
            confidence=confidence,
        )
        mappings.append(mapping)

        if confidence == "none":
            uncovered.append(sym)

    covered_count = sum(1 for m in mappings if m.confidence != "none")
    coverage_ratio = covered_count / len(mappings) if mappings else 0.0

    return CoverageReport(
        mappings=mappings,
        uncovered_symbols=uncovered,
        coverage_ratio=coverage_ratio,
    )
