"""Phase 8 protocol types."""

from dataclasses import dataclass
from enum import Enum


class Phase8Arm(str, Enum):
    INITIAL = "initial"
    RETRY_CONTROL = "retry_control"
    FEEDBACK = "feedback"


@dataclass(frozen=True)
class Phase8Prompt:
    template_version: str
    arm: Phase8Arm
    system: str
    user: str
    prompt_hash: str


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason: str
    failed_base_tests: tuple[str, ...] = ()
    failed_feedback_tests: tuple[str, ...] = ()
