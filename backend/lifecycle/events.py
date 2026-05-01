"""Lifecycle event names for logs/telemetry (structured, no side effects)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TASK_CREATED = "task_created"
TASK_STATUS_CHANGED = "task_status_changed"
PLAN_REVISION_CREATED = "plan_revision_created"
RUN_CREATED = "run_created"
RUN_METRIC_LOGGED = "run_metric_logged"
JOB_QUEUED = "job_queued"
JOB_CLAIMED = "job_claimed"
JOB_COMPLETED = "job_completed"
JOB_FAILED = "job_failed"
ARTIFACT_REGISTERED = "artifact_registered"
GATE_EVALUATED = "gate_evaluated"
APPROVAL_REQUESTED = "approval_requested"
APPROVAL_DECIDED = "approval_decided"
MEMORY_CREATED = "memory_created"


def emit_lifecycle_event(name: str, **fields: Any) -> None:
    """Log a single-line structured lifecycle event."""
    parts = " ".join(f"{k}={v!r}" for k, v in sorted(fields.items()) if v is not None)
    logger.info("lifecycle_event %s %s", name, parts)
