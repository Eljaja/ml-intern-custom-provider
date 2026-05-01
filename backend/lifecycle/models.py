"""Domain enums and ID generation for the lifecycle layer."""

from __future__ import annotations

import uuid
from enum import Enum


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class TaskPhase(str, Enum):
    INTAKE = "intake"
    PLANNING = "planning"
    DATA_INSPECTION = "data_inspection"
    EXPERIMENTING = "experimenting"
    EVALUATION = "evaluation"
    ARTIFACT_REVIEW = "artifact_review"
    RELEASE = "release"


class ExperimentRunType(str, Enum):
    RESEARCH = "research"
    TRAINING = "training"
    EVALUATION = "evaluation"
    SWEEP = "sweep"
    DEPLOYMENT_CANDIDATE = "deployment_candidate"
    BENCHMARK = "benchmark"


class ExperimentRunStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class GateResultStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"


class MemoryScope(str, Enum):
    TASK = "task"
    PROJECT = "project"
    GLOBAL = "global"


class MemoryKind(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    LESSON = "lesson"
    DATASET_PROFILE = "dataset_profile"
    ERROR_SIGNATURE = "error_signature"
    RETRIEVAL_CHUNK = "retrieval_chunk"
    METRIC_SUMMARY = "metric_summary"


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


def new_external_id(kind: str) -> str:
    """Return a stable external id like ``tsk_<hex>``."""
    prefix = kind.strip().lower()
    if not prefix.endswith("_"):
        prefix = f"{prefix}_"
    # 16 hex chars (~64-bit) keeps URLs short; uniqueness per task scope is enough for P0
    return f"{prefix}{uuid.uuid4().hex[:16]}"
