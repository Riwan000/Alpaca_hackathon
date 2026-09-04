"""Per-node retry + failure classification — tasks P6-BE-8 and P6-BE-9.

Two mechanisms the orchestrator graph leans on, kept together because they meet
at one point: a retry that has exhausted its budget hands the *cause* to the
classifier, which decides whether the cycle degrades or halts.

P6-BE-8 — :class:`RetryPolicy` / :func:`run_with_retry`
    A bounded, backing-off retry around any callable. A *transient* failure
    (:class:`TransientError`, or whatever ``retry_on`` matches) is retried up to
    ``max_attempts`` with an exponential, capped delay; anything else propagates
    immediately. When the final attempt still fails the last exception is
    re-raised wrapped in :class:`RetriesExhausted` — a bounded outcome, never an
    infinite loop.

P6-BE-9 — :class:`FailureClass` / :func:`classify_failure`  (BRD §31)
    ``CRITICAL`` → *do not trade*: portfolio unavailable, stale/invalid options
    data, risk engine unavailable, invalid execution state, a broker auth
    failure. The cycle halts before ``EXECUTION``.
    ``RECOVERABLE`` → degrade the context, record the limitation, carry on: a
    news source down, one enrichment source unavailable, a non-critical analysis
    failure.

Callers can be unambiguous by raising :class:`CriticalFailure` /
:class:`RecoverableFailure`; otherwise the classifier falls back to the
exception type and the node ``stage`` it happened in, and — when it still cannot
tell — to ``CRITICAL`` (fail safe: when in doubt, do not trade).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from backend.agents.base import AgentError
from backend.integrations.alpaca.client import AlpacaCredentialsError, AlpacaError
from backend.models.enums import WorkflowNode

__all__ = [
    "TransientError",
    "CriticalFailure",
    "RecoverableFailure",
    "RetryPolicy",
    "RetriesExhausted",
    "run_with_retry",
    "FailureClass",
    "classify_failure",
    "is_transient",
]

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# --------------------------------------------------------------------------- #
# markers
# --------------------------------------------------------------------------- #


class TransientError(RuntimeError):
    """Opt-in marker: a failure worth retrying (timeout, 429, 5xx, reset)."""


class CriticalFailure(RuntimeError):
    """Opt-in marker: unambiguously halt the cycle — never reach the broker."""


class RecoverableFailure(RuntimeError):
    """Opt-in marker: a soft failure — degrade the context and carry on."""


# --------------------------------------------------------------------------- #
# P6-BE-8 — bounded retry with backoff
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetryPolicy:
    """How many times, and how long between, to retry a transient failure.

    ``delay_for(n)`` is the wait *after* the n-th (1-based) attempt fails:
    ``base_delay_s * backoff ** (n - 1)``, capped at ``max_delay_s``. With the
    defaults: attempt 1 fails → wait 0.5s, attempt 2 fails → wait 1.0s, attempt 3
    is the last (``max_attempts``) so there is no wait after it — the cycle gets
    a :class:`RetriesExhausted`.
    """

    max_attempts: int = 3
    base_delay_s: float = 0.5
    backoff: float = 2.0
    max_delay_s: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_s < 0 or self.max_delay_s < 0:
            raise ValueError("delays must be non-negative")

    def delay_for(self, attempt: int) -> float:
        """Seconds to wait after ``attempt`` (1-based) has failed."""
        exp = self.base_delay_s * (self.backoff ** max(0, attempt - 1))
        return float(min(self.max_delay_s, exp))


class RetriesExhausted(RuntimeError):
    """Every attempt failed. Carries the last exception as :attr:`cause`."""

    def __init__(self, cause: BaseException, attempts: int) -> None:
        super().__init__(
            f"retries exhausted after {attempts} attempt(s): "
            f"{type(cause).__name__}: {cause}"
        )
        self.cause = cause
        self.attempts = attempts


def _matches(exc: BaseException, retry_on: Any) -> bool:
    if callable(retry_on) and not isinstance(retry_on, type):
        return bool(retry_on(exc))
    if isinstance(retry_on, type):
        return isinstance(exc, retry_on)
    if isinstance(retry_on, Iterable):
        return isinstance(exc, tuple(retry_on))
    return False


def run_with_retry(
    fn: Callable[[], _T],
    *,
    policy: RetryPolicy | None = None,
    retry_on: Any = TransientError,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> _T:
    """Call ``fn`` and retry it on a transient failure, bounded by ``policy``.

    ``retry_on`` is an exception type, a tuple of them, or a predicate
    ``(exc) -> bool``; a non-matching exception propagates immediately, unchanged.
    When the last attempt still fails the cause is re-raised inside
    :class:`RetriesExhausted` — the loop is bounded by ``policy.max_attempts`` and
    never spins.

    ``sleep`` is injectable so tests assert on the backoff schedule without
    waiting; ``on_retry(attempt, exc, delay)`` is a hook for the same.
    """
    pol = policy or RetryPolicy()
    last: BaseException | None = None
    for attempt in range(1, pol.max_attempts + 1):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised below; we only branch on it
            if not _matches(exc, retry_on):
                raise
            last = exc
            if attempt == pol.max_attempts:
                break
            delay = pol.delay_for(attempt)
            logger.warning(
                "transient failure on attempt %d/%d (%s); retrying in %.2fs",
                attempt,
                pol.max_attempts,
                type(exc).__name__,
                delay,
            )
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            if delay > 0:
                sleep(delay)
    assert last is not None  # loop ran at least once
    raise RetriesExhausted(last, pol.max_attempts) from last


# --------------------------------------------------------------------------- #
# P6-BE-9 — failure classifier (BRD §31)
# --------------------------------------------------------------------------- #


class FailureClass(str, Enum):
    """BRD §31 split. ``CRITICAL`` halts the cycle; ``RECOVERABLE`` degrades it."""

    CRITICAL = "CRITICAL"
    RECOVERABLE = "RECOVERABLE"


#: Substrings in an :class:`AlpacaError` message that mean "credentials / perms",
#: not "the venue had a bad minute".
_AUTH_MARKERS: tuple[str, ...] = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "invalid credential",
    "invalid api key",
    "authentication",
    "access key",
)

#: Stages where *any* unexplained failure means "do not trade" — the risk gate
#: and the broker leg. A wobble here is never something to degrade past.
_CRITICAL_STAGES: frozenset[str] = frozenset(
    {WorkflowNode.RISK_CHECK.value, WorkflowNode.EXECUTION.value}
)
#: Stages whose default is "degrade" — the analysis pipeline.
_RECOVERABLE_STAGES: frozenset[str] = frozenset(
    {WorkflowNode.ANALYZING.value, WorkflowNode.STRATEGY_EVALUATION.value}
)


def _looks_like_auth(exc: AlpacaError) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _AUTH_MARKERS)


def is_transient(exc: BaseException) -> bool:
    """Best-effort "is this worth a retry?" — a marker, or a venue 429 / 5xx / timeout.

    Used as the default retry predicate for broker calls; auth failures are
    explicitly *not* transient (a retry cannot fix a bad key).
    """
    if isinstance(exc, TransientError):
        return True
    if isinstance(exc, (CriticalFailure, RecoverableFailure, AlpacaCredentialsError)):
        return False
    if isinstance(exc, AlpacaError):
        if _looks_like_auth(exc):
            return False
        msg = str(exc).lower()
        return any(m in msg for m in ("429", "500", "502", "503", "504", "timeout", "timed out"))
    return False


def classify_failure(exc: BaseException, *, stage: str | WorkflowNode | None = None) -> FailureClass:
    """Decide whether ``exc`` (raised in node ``stage``) halts or degrades the cycle.

    Order: explicit marker → known exception type → the stage it happened in →
    ``CRITICAL`` as the safe default. A :class:`RetriesExhausted` is unwrapped and
    its cause classified.
    """
    if isinstance(exc, RetriesExhausted):
        exc = exc.cause

    stage_val = stage.value if isinstance(stage, WorkflowNode) else (str(stage) if stage else None)

    if isinstance(exc, CriticalFailure):
        return FailureClass.CRITICAL
    if isinstance(exc, RecoverableFailure):
        return FailureClass.RECOVERABLE

    # Broker credentials / permissions — a retry cannot fix it, and BRD §31 lists
    # "portfolio unavailable" and an invalid execution state as critical.
    if isinstance(exc, AlpacaCredentialsError):
        return FailureClass.CRITICAL
    if isinstance(exc, AlpacaError) and _looks_like_auth(exc):
        return FailureClass.CRITICAL

    # A single analysis agent falling over is the textbook recoverable case
    # ("news unavailable", "one enrichment source unavailable").
    if isinstance(exc, AgentError):
        return FailureClass.RECOVERABLE

    if stage_val in _CRITICAL_STAGES:
        return FailureClass.CRITICAL
    if stage_val in _RECOVERABLE_STAGES:
        return FailureClass.RECOVERABLE

    return FailureClass.CRITICAL
