"""Durable ML lifecycle API (control plane)."""

from __future__ import annotations

from typing import Annotated, Any

from dependencies import get_current_user
from fastapi import APIRouter, Depends
from lifecycle.schemas import (
    ArtifactCreateRequest,
    ArtifactResponse,
    ExperimentRunCreateRequest,
    ExperimentRunResponse,
    JobCreateRequest,
    JobResponse,
    TaskCreateRequest,
    TaskDetailResponse,
    TaskPatchRequest,
    TaskSummaryResponse,
)
from lifecycle.service import LifecycleService, get_lifecycle_service

router = APIRouter(prefix="/api/v2", tags=["lifecycle-v2"])


def get_lifecycle_dep() -> LifecycleService:
    return get_lifecycle_service()


def _user_id(user: dict[str, Any]) -> str:
    return str(user.get("user_id") or "dev")


LifecycleSvc = Annotated[LifecycleService, Depends(get_lifecycle_dep)]
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


@router.post("/tasks", response_model=TaskSummaryResponse)
async def v2_create_task(body: TaskCreateRequest, user: CurrentUser, svc: LifecycleSvc) -> TaskSummaryResponse:
    return svc.create_task(_user_id(user), body)


@router.get("/tasks", response_model=list[TaskSummaryResponse])
async def v2_list_tasks(user: CurrentUser, svc: LifecycleSvc) -> list[TaskSummaryResponse]:
    return svc.list_tasks(_user_id(user))


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def v2_get_task(task_id: str, user: CurrentUser, svc: LifecycleSvc) -> TaskDetailResponse:
    return svc.get_task_detail(_user_id(user), task_id)


@router.patch("/tasks/{task_id}", response_model=TaskSummaryResponse)
async def v2_patch_task(
    task_id: str, body: TaskPatchRequest, user: CurrentUser, svc: LifecycleSvc
) -> TaskSummaryResponse:
    return svc.patch_task(_user_id(user), task_id, body)


@router.post("/tasks/{task_id}/runs", response_model=ExperimentRunResponse)
async def v2_create_run(
    task_id: str, body: ExperimentRunCreateRequest, user: CurrentUser, svc: LifecycleSvc
) -> ExperimentRunResponse:
    return svc.create_run(_user_id(user), task_id, body)


@router.get("/tasks/{task_id}/runs", response_model=list[ExperimentRunResponse])
async def v2_list_runs(task_id: str, user: CurrentUser, svc: LifecycleSvc) -> list[ExperimentRunResponse]:
    return svc.list_runs(_user_id(user), task_id)


@router.post("/tasks/{task_id}/jobs", response_model=JobResponse)
async def v2_create_job(
    task_id: str, body: JobCreateRequest, user: CurrentUser, svc: LifecycleSvc
) -> JobResponse:
    return svc.create_job(_user_id(user), task_id, body)


@router.get("/tasks/{task_id}/jobs", response_model=list[JobResponse])
async def v2_list_jobs(task_id: str, user: CurrentUser, svc: LifecycleSvc) -> list[JobResponse]:
    return svc.list_jobs(_user_id(user), task_id)


@router.post("/tasks/{task_id}/artifacts", response_model=ArtifactResponse)
async def v2_create_artifact(
    task_id: str, body: ArtifactCreateRequest, user: CurrentUser, svc: LifecycleSvc
) -> ArtifactResponse:
    return svc.create_artifact(_user_id(user), task_id, body)


@router.get("/tasks/{task_id}/artifacts", response_model=list[ArtifactResponse])
async def v2_list_artifacts(task_id: str, user: CurrentUser, svc: LifecycleSvc) -> list[ArtifactResponse]:
    return svc.list_artifacts(_user_id(user), task_id)
