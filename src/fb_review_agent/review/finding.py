"""Finding data model for code review results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    SECURITY = "security"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    CONCURRENCY = "concurrency"


@dataclass
class CodeReference:
    """A specific code snippet referenced by a finding."""

    file: str
    line_start: int
    line_end: int
    snippet: str
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> CodeReference:
        return cls(
            file=data.get("file", ""),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            snippet=data.get("snippet", ""),
            label=data.get("label", ""),
        )


@dataclass
class Finding:
    """A single code review finding backed by evidence."""

    id: str
    severity: Severity
    confidence: Confidence
    title: str
    file: str
    line_start: int
    line_end: int
    description: str
    evidence_chain: list[str] = field(default_factory=list)
    references: list[CodeReference] = field(default_factory=list)
    suggestion: str = ""
    category: Category = Category.CORRECTNESS

    @classmethod
    def from_dict(cls, data: dict) -> Finding:
        refs = [CodeReference.from_dict(r) for r in data.get("references", [])]
        return cls(
            id=data.get("id", "F?"),
            severity=Severity(data.get("severity", "low")),
            confidence=Confidence(data.get("confidence", "low")),
            title=data.get("title", ""),
            file=data.get("file", ""),
            line_start=data.get("line_start", 0),
            line_end=data.get("line_end", 0),
            description=data.get("description", ""),
            evidence_chain=data.get("evidence_chain", []),
            references=refs,
            suggestion=data.get("suggestion", ""),
            category=Category(data.get("category", "correctness")),
        )


@dataclass
class ReviewSummary:
    """Summary statistics from a review."""

    total_files_reviewed: int = 0
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    premises_established: int = 0
    traces_performed: int = 0
    claims_investigated: int = 0
    claims_refuted: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> ReviewSummary:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ReviewResult:
    """Complete review result including findings, summary, and reasoning log."""

    findings: list[Finding] = field(default_factory=list)
    summary: ReviewSummary = field(default_factory=ReviewSummary)
    reasoning_log: str = ""
    raw_response: str = ""

    @classmethod
    def from_parsed(cls, data: dict, raw_response: str = "") -> ReviewResult:
        findings = [Finding.from_dict(f) for f in data.get("findings", [])]
        summary = ReviewSummary.from_dict(data.get("summary", {}))
        return cls(
            findings=findings,
            summary=summary,
            reasoning_log=data.get("reasoning_log", ""),
            raw_response=raw_response,
        )
