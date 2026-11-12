"""The result of one quality check, shared by every checker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS", "WARN" or "FAIL"
    details: list[str]
