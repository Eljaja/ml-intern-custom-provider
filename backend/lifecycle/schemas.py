"""Pydantic schemas for /api/v2 lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from lifecycle.models import (
    ExperimentRunStatus,
    ExperimentRunType,
    JobStatus,
    TaskPhase,
    TaskStatus,
)

# --- Task -----------------------------------------------------------------


class TaskCreateRequest(BaseModel):
    title: str = Field(default="", max_length=512)
    goal: str = Field(min_length=1, max_length=32_000)
    source_session_id: str | None = Field(default=None, max_length=128)
    phase: TaskPhase = TaskPhase.INTAKE
    status: TaskStatus = TaskStatus.DRAFT
    priority: int = 0
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    autonomy_mode: Literal["manual", "supervised", "bounded", "full"] = "supervised"
    constraints: dict[str, Any] = Field(default_factory=dict)
    acceptance: dict[str, Any] = Field(default_factory=dict)


class TaskPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    goal: str | None = Field(default=None, max_length=32_000)
    source_session_id: str | None = None
    phase: TaskPhase | None = None
    status: TaskStatus | None = None
    priority: int | None = None
    risk_level: Literal["low", "medium", "high", "critical"] | None = None
    autonomy_mode: Literal["manual", "supervised", "bounded", "full"] | None = None
    constraints: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    current_run_id: str | None = None
    latest_plan_revision_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskSummaryResponse(BaseModel):
    id: str
    owner_user_id: str
    source_session_id: str | None = None
    title: str
    goal: str
    status: str
    phase: str
    priority: int
    risk_level: str
    autonomy_mode: str
    current_run_id: str | None = None
    latest_plan_revision_id: str | None = None
    created_at: str
    updated_at: str


class TaskDetailResponse(TaskSummaryResponse):
    constraints: dict[str, Any]
    acceptance: dict[str, Any]
    started_at: str | None = None
    finished_at: str | None = None
    runs: list["ExperimentRunResponse"]
    jobs: list["JobResponse"]
    artifacts: list["ArtifactResponse"]


# --- Experiment run -------------------------------------------------------


class ExperimentRunCreateRequest(BaseModel):
    run_type: ExperimentRunType = ExperimentRunType.RESEARCH
    status: ExperimentRunStatus = ExperimentRunStatus.PLANNED
    parent_run_id: str | None = None
    model_name: str | None = None
    dataset_artifact_id: str | None = None
    model_artifact_id: str | None = None
    code_version: str | None = None
    executor_type: str | None = "local_safe"
    repro_command: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunResponse(BaseModel):
    id: str
    task_id: str
    parent_run_id: str | None = None
    run_type: str
    status: str
    model_name: str | None = None
    dataset_artifact_id: str | None = None
    model_artifact_id: str | None = None
    code_version: str | None = None
    executor_type: str | None = None
    repro_command: str | None = None
    config: dict[str, Any]
    metrics: dict[str, Any]
    summary: dict[str, Any]
    cost: dict[str, Any]
    failure_reason: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


# --- Job ------------------------------------------------------------------


class JobCreateRequest(BaseModel):
    run_id: str | None = None
    queue_name: str = Field(default="default", max_length=128)
    job_type: str = Field(min_length=1, max_length=128)
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0
    idempotency_key: str | None = Field(default=None, max_length=256)
    executor_type: str | None = "mock"
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=32)


class JobResponse(BaseModel):
    id: str
    task_id: str
    run_id: str | None = None
    queue_name: str
    job_type: str
    status: str
    priority: int
    idempotency_key: str | None = None
    executor_type: str | None = None
    payload: dict[str, Any]
    result: dict[str, Any]
    checkpoint_uri: str | None = None
    attempt_count: int
    max_attempts: int
    next_attempt_at: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    last_error: str | None = None
    created_by: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


# --- Artifact -----------------------------------------------------------


class ArtifactCreateRequest(BaseModel):
    run_id: str | None = None
    job_id: str | None = None
    type: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=512)
    version: str | None = Field(default=None, max_length=128)
    uri: str = Field(min_length=1, max_length=8_000)
    storage_backend: str = Field(default="local_file", max_length=64)
    content_type: str | None = Field(default=None, max_length=256)
    sha256: str | None = Field(default=None, max_length=128)
    size_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactResponse(BaseModel):
    id: str
    task_id: str
    run_id: str | None = None
    job_id: str | None = None
    type: str
    name: str
    version: str | None = None
    uri: str
    storage_backend: str
    content_type: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any]
    created_by: str | None = None
    created_at: str


class ApiErrorDetail(BaseModel):
    error: str
    message: str
