"""
core/qa/qa_model.py

QA data model for the wastewater planning platform.
QAFinding  — a single validation finding (FAIL / WARN / INFO)
QAResult   — the aggregated output of a full QA run
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


class Severity:
    FAIL = "FAIL"    # export blocked
    WARN = "WARN"    # export with warning banner
    INFO = "INFO"    # informational only


@dataclass
class QAFinding:
    code:           str
    category:       str
    severity:       str
    message:        str
    scenario:       Optional[str] = None
    metric:         Optional[str] = None
    expected:       Optional[str] = None
    actual:         Optional[str] = None
    recommendation: Optional[str] = None

    @property
    def icon(self) -> str:
        return {"FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️"}.get(self.severity, "•")

    def __str__(self) -> str:
        prefix = f"[{self.code}] " if self.code else ""
        scen = f"({self.scenario}) " if self.scenario else ""
        return f"{self.icon} {prefix}{scen}{self.message}"


@dataclass
class QAResult:
    findings: List[QAFinding] = field(default_factory=list)

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARN)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    @property
    def passed(self) -> bool:
        return self.fail_count == 0

    @property
    def export_ready(self) -> bool:
        return self.fail_count == 0

    @property
    def status_icon(self) -> str:
        if self.fail_count > 0:  return "❌"
        if self.warn_count > 0:  return "⚠️"
        return "✅"

    @property
    def status_label(self) -> str:
        if self.fail_count > 0:
            return f"QA FAILED — {self.fail_count} critical issue(s)"
        if self.warn_count > 0:
            return f"QA PASSED with {self.warn_count} warning(s)"
        return "QA PASSED — all checks clear"

    def fails(self):  return [f for f in self.findings if f.severity == Severity.FAIL]
    def warns(self):  return [f for f in self.findings if f.severity == Severity.WARN]
    def infos(self):  return [f for f in self.findings if f.severity == Severity.INFO]

    def by_scenario(self, name: str) -> "QAResult":
        return QAResult(findings=[f for f in self.findings
                                   if f.scenario == name or f.scenario is None])

    def merge(self, other: "QAResult") -> "QAResult":
        return QAResult(findings=self.findings + other.findings)
