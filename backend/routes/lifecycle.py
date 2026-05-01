"""Durable ML lifecycle API routes.

These endpoints expose the state layer required for an autonomous ML agent:
persistent tasks, experiment runs, execution jobs, and produced artifacts.
"""

from __future__ import annotations

from typing import Any, Literal

from dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lifecycle_store import lifecycle_store


router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])


TaskStatus = Literal["active", "blocked", "completed", "cancelled"]
TaskPhase = Literal[
    "intake",
    "planning",
    "data_inspection",
    "experimenting",
    "evaluation",
    "artifact_review",
    "release",
]
ExperimentStatus = Literal["planned", "running", "succeeded", "failed", "cancelled"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class PlanItem(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"] = "pending"


class TaskCreateRequest(BaseModel):
    goal: str = Field(min_length=3)
    constraints: dict[str, Any] = Field(default_factory=dict)
    success_metrics: dict[str, Any] = Field(default_factory=dict)
    plan: list[PlanItem] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    goal: str | None = None
    constraints: dict[str, Any] | None = None
    success_metrics: dict[str, Any] | None = None
    plan: list[PlanItem] | None = None
    current_phase: TaskPhase | None = None
    status: TaskStatus | None = None
    last_decision: str | None = None


class ExperimentCreateRequest(BaseModel):
    hypothesis: str = Field(min_length=3)
    dataset_version: str | None = None
    model_id: str | None = None
    training_config: dict[str, Any] = Field(default_factory=dict)


class ExperimentUpdateRequest(BaseModel):
    hypothesis: str | None = None
    dataset_version: str | None = None
    model_id: str | None = None
    training_config: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    status: ExperimentStatus | None = None
    failure_reason: str | None = None


class JobCreateRequest(BaseModel):
    kind: str = Field(min_length=2)
    experiment_id: str | None = None
    command: str | None = None
    hardware: str | None = None
    status: JobStatus = "queued"


class JobUpdateRequest(BaseModel):
    kind: str | None = None
    command: str | None = None
    hardware: str | None = None
    status: JobStatus | None = None
    logs_uri: str | None = None
    error: str | None = None


class ArtifactCreateRequest(BaseModel):
    type: str = Field(min_length=2)
    uri: str = Field(min_length=3)
    experiment_id: str | None = None
    job_id: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _user_id(user: dict[str, Any]) -> str:
    return str(user.get("user_id") or "dev")


def _model_dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(exclude_unset=True, mode="json")


@router.get("/tasks")
async def list_lifecycle_tasks(user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    return lifecycle_store.list_tasks(user_id=_user_id(user))


@router.post("/tasks")
async def create_lifecycle_task(
    body: TaskCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    return lifecycle_store.create_task(
        user_id=_user_id(user),
        goal=body.goal,
        constraints=body.constraints,
        success_metrics=body.success_metrics,
        plan=[item.model_dump(mode="json") for item in body.plan],
    )


@router.get("/tasks/{task_id}")
async def get_lifecycle_task(
    task_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    task = lifecycle_store.get_task(user_id=_user_id(user), task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Lifecycle task not found")
    return task


@router.patch("/tasks/{task_id}")
async def update_lifecycle_task(
    task_id: str,
    body: TaskUpdateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    updates = _model_dump(body)
    if "plan" in updates and updates["plan"] is not None:
        updates["plan"] = [item.model_dump(mode="json") for item in body.plan or []]
    task = lifecycle_store.update_task(user_id=_user_id(user), task_id=task_id, updates=updates)
    if not task:
        raise HTTPException(status_code=404, detail="Lifecycle task not found")
    return task


@router.post("/tasks/{task_id}/experiments")
async def create_lifecycle_experiment(
    task_id: str,
    body: ExperimentCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    experiment = lifecycle_store.create_experiment(
        user_id=_user_id(user),
        task_id=task_id,
        hypothesis=body.hypothesis,
        dataset_version=body.dataset_version,
        model_id=body.model_id,
        training_config=body.training_config,
    )
    if not experiment:
        raise HTTPException(status_code=404, detail="Lifecycle task not found")
    return experiment


@router.patch("/experiments/{experiment_id}")
async def update_lifecycle_experiment(
    experiment_id: str,
    body: ExperimentUpdateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    experiment = lifecycle_store.update_experiment(
        user_id=_user_id(user),
        experiment_id=experiment_id,
        updates=_model_dump(body),
    )
    if not experiment:
        raise HTTPException(status_code=404, detail="Lifecycle experiment not found")
    return experiment


@router.post("/tasks/{task_id}/jobs")
async def create_lifecycle_job(
    task_id: str,
    body: JobCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    job = lifecycle_store.create_job(
        user_id=_user_id(user),
        task_id=task_id,
        kind=body.kind,
        experiment_id=body.experiment_id,
        command=body.command,
        hardware=body.hardware,
        status=body.status,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Lifecycle task not found")
    return job


@router.patch("/jobs/{job_id}")
async def update_lifecycle_job(
    job_id: str,
    body: JobUpdateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    job = lifecycle_store.update_job(user_id=_user_id(user), job_id=job_id, updates=_model_dump(body))
    if not job:
        raise HTTPException(status_code=404, detail="Lifecycle job not found")
    return job


@router.post("/tasks/{task_id}/artifacts")
async def create_lifecycle_artifact(
    task_id: str,
    body: ArtifactCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    artifact = lifecycle_store.create_artifact(
        user_id=_user_id(user),
        task_id=task_id,
        type=body.type,
        uri=body.uri,
        experiment_id=body.experiment_id,
        job_id=body.job_id,
        checksum=body.checksum,
        metadata=body.metadata,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Lifecycle task not found")
    return artifact
