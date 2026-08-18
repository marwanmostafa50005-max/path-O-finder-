"""Closed-loop confirmation — MANUAL doctor/RN step (approved core design).

The core build performs NO PMS database read. The operator, looking at the
practice software in front of them, confirms per flag whether the loop is
closed. Two conditions define "closed", per practice settings:

  INBOX  — the result is processed/signed in the doctor's results inbox
  RECALL — a recall/reminder exists for it

Strictness: STRICT = BOTH must hold; LENIENT = EITHER suffices.

ClosedLoopChecker is the SEAM for any future (separately parked) PMS read:
implement its interface, never touch anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mode(str, Enum):
    INBOX = "inbox"
    RECALL = "recall"


class Strictness(str, Enum):
    STRICT = "strict"
    LENIENT = "lenient"


@dataclass(frozen=True)
class ClosedLoopSettings:
    mode: Mode = Mode.INBOX
    strictness: Strictness = Strictness.STRICT

    @property
    def label(self) -> str:
        return f"{self.mode.value}/{self.strictness.value}"


@dataclass(frozen=True)
class LoopEvidence:
    """What the human operator observed in the PMS for one flag."""
    inbox_actioned: bool | None = None    # None = not checked / unknown
    recall_exists: bool | None = None


def is_closed(evidence: LoopEvidence, settings: ClosedLoopSettings) -> tuple[bool, str]:
    """Returns (closed, why_no_action_evidence). Unknown never counts as
    closed — absence of evidence is treated as an open loop (paranoid engine)."""
    inbox = evidence.inbox_actioned is True
    recall = evidence.recall_exists is True

    if settings.strictness == Strictness.STRICT:
        closed = inbox and recall
        missing = []
        if not inbox:
            missing.append("result not processed/signed in inbox")
        if not recall:
            missing.append("no recall/reminder recorded")
        why = "; ".join(missing) if missing else "both conditions met"
    else:
        closed = inbox or recall
        why = ("neither inbox action nor recall found"
               if not closed else "at least one condition met")
    return closed, why


class ClosedLoopChecker:
    """Interface seam for a future PMS-read integration (PARKED — do not
    implement a PMS read in the core build). The manual implementation is the
    human disposition itself; automated implementations must subclass this."""

    def check(self, flag: dict) -> LoopEvidence:  # pragma: no cover - interface
        raise NotImplementedError


class ManualChecker(ClosedLoopChecker):
    """Core-build checker: no evidence is ever auto-derived; every flag stays
    open until a human records a disposition."""

    def check(self, flag: dict) -> LoopEvidence:
        return LoopEvidence(inbox_actioned=None, recall_exists=None)
