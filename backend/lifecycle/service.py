"""Business logic and authorization for lifecycle APIs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from lifecycle import events
from lifecycle.models import new_external_id
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
from lifecycle.store import LifecycleStore


def _iso_or_none(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _public_error(code: str, message: str) -> dict[str, Any]:
    return {"error": code, "message": message}


class LifecycleService:
    def __init__(self, store: LifecycleStore | None = None) -> None:
        self.store = store or LifecycleStore()

    def _require_task(self, owner_user_id: str, task_id: str) -> dict[str, Any]:
        task = self.store.get_task_by_id(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_public_error("task_not_found", f"Unknown task {task_id}"),
            )
        if task["owner_user_id"] != owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_public_error("forbidden", "You do not have access to this task"),
            )
        return task

    def _require_run(self, owner_user_id: str, task_id: str, run_id: str) -> dict[str, Any]:
        self._require_task(owner_user_id, task_id)
        run = self.store.get_run_by_id(run_id)
        if run is None or run["task_id"] != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_public_error("run_not_found", f"Unknown run {run_id} for this task"),
            )
        return run

    def _require_job(self, owner_user_id: str, task_id: str, job_id: str) -> dict[str, Any]:
        self._require_task(owner_user_id, task_id)
        job = self.store.get_job_by_id(job_id)
        if job is None or job["task_id"] != task_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_public_error("job_not_found", f"Unknown job {job_id} for this task"),
            )
        return job

    def create_task(self, owner_user_id: str, body: TaskCreateRequest) -> TaskSummaryResponse:
        task_id = new_external_id("tsk")
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": task_id,
            "owner_user_id": owner_user_id,
            "source_session_id": body.source_session_id,
            "title": body.title,
            "goal": body.goal,
            "status": body.status.value,
            "phase": body.phase.value,
            "priority": body.priority,
            "risk_level": body.risk_level,
            "autonomy_mode": body.autonomy_mode,
            "constraints": body.constraints,
            "acceptance": body.acceptance,
            "current_run_id": None,
            "latest_plan_revision_id": None,
            "created_at": now,
            "updated_at": now,
        }
        created = self.store.insert_task(row)
        events.emit_lifecycle_event(events.TASK_CREATED, task_id=task_id, owner=owner_user_id)
        return self._task_summary(created)

    def list_tasks(self, owner_user_id: str) -> list[TaskSummaryResponse]:
        rows = self.store.list_tasks_for_owner(owner_user_id)
        return [self._task_summary(r) for r in rows]

    def get_task_detail(self, owner_user_id: str, task_id: str) -> TaskDetailResponse:
        task = self._require_task(owner_user_id, task_id)
        runs = [self._run_response(r) for r in self.store.list_runs_for_task(task_id)]
        jobs = [self._job_response(j) for j in self.store.list_jobs_for_task(task_id)]
        arts = [self._artifact_response(a) for a in self.store.list_artifacts_for_task(task_id)]
        return TaskDetailResponse(
            **self._task_summary(task).model_dump(),
            constraints=task["constraints"],
            acceptance=task["acceptance"],
            started_at=task.get("started_at"),
            finished_at=task.get("finished_at"),
            runs=runs,
            jobs=jobs,
            artifacts=arts,
        )

    def patch_task(self, owner_user_id: str, task_id: str, body: TaskPatchRequest) -> TaskSummaryResponse:
        self._require_task(owner_user_id, task_id)
        patch = body.model_dump(exclude_unset=True)
        if not patch:
            task = self.store.get_task_by_id(task_id)
            return self._task_summary(task)
        updates: dict[str, Any] = {}
        if "title" in patch:
            updates["title"] = patch["title"]
        if "goal" in patch:
            updates["goal"] = patch["goal"]
        if "source_session_id" in patch:
            updates["source_session_id"] = patch["source_session_id"]
        if "phase" in patch and patch["phase"] is not None:
            updates["phase"] = patch["phase"].value
        if "status" in patch and patch["status"] is not None:
            updates["status"] = patch["status"].value
        if "priority" in patch:
            updates["priority"] = patch["priority"]
        if "risk_level" in patch:
            updates["risk_level"] = patch["risk_level"]
        if "autonomy_mode" in patch:
            updates["autonomy_mode"] = patch["autonomy_mode"]
        if "constraints" in patch:
            updates["constraints"] = patch["constraints"]
        if "acceptance" in patch:
            updates["acceptance"] = patch["acceptance"]
        if "current_run_id" in patch:
            updates["current_run_id"] = patch["current_run_id"]
        if "latest_plan_revision_id" in patch:
            updates["latest_plan_revision_id"] = patch["latest_plan_revision_id"]
        if "started_at" in patch:
            updates["started_at"] = _iso_or_none(patch["started_at"])
        if "finished_at" in patch:
            updates["finished_at"] = _iso_or_none(patch["finished_at"])
        updated = self.store.update_task(task_id, updates)
        events.emit_lifecycle_event(
            events.TASK_STATUS_CHANGED,
            task_id=task_id,
            status=updated.get("status"),
            phase=updated.get("phase"),
        )
        return self._task_summary(updated)

    def create_run(
        self, owner_user_id: str, task_id: str, body: ExperimentRunCreateRequest
    ) -> ExperimentRunResponse:
        self._require_task(owner_user_id, task_id)
        run_id = new_external_id("run")
        if body.parent_run_id:
            self._require_run(owner_user_id, task_id, body.parent_run_id)
        row = {
            "id": run_id,
            "task_id": task_id,
            "parent_run_id": body.parent_run_id,
            "run_type": body.run_type.value,
            "status": body.status.value,
            "model_name": body.model_name,
            "dataset_artifact_id": body.dataset_artifact_id,
            "model_artifact_id": body.model_artifact_id,
            "code_version": body.code_version,
            "executor_type": body.executor_type,
            "repro_command": body.repro_command,
            "config": body.config,
            "metrics": body.metrics,
            "summary": body.summary,
            "cost": body.cost,
            "failure_reason": None,
        }
        created = self.store.insert_run(row)
        events.emit_lifecycle_event(events.RUN_CREATED, task_id=task_id, run_id=run_id)
        return self._run_response(created)

    def list_runs(self, owner_user_id: str, task_id: str) -> list[ExperimentRunResponse]:
        self._require_task(owner_user_id, task_id)
        return [self._run_response(r) for r in self.store.list_runs_for_task(task_id)]

    def create_job(
        self, owner_user_id: str, task_id: str, body: JobCreateRequest
    ) -> JobResponse:
        self._require_task(owner_user_id, task_id)
        if body.run_id:
            self._require_run(owner_user_id, task_id, body.run_id)
        if body.idempotency_key:
            existing = self.store.find_job_by_idempotency(task_id, body.idempotency_key)
            if existing:
                return self._job_response(existing)
        job_id = new_external_id("job")
        row = {
            "id": job_id,
            "task_id": task_id,
            "run_id": body.run_id,
            "queue_name": body.queue_name,
            "job_type": body.job_type,
            "status": body.status.value,
            "priority": body.priority,
            "idempotency_key": body.idempotency_key,
            "executor_type": body.executor_type,
            "payload": body.payload,
            "result": {},
            "attempt_count": 0,
            "max_attempts": body.max_attempts,
            "created_by": owner_user_id,
        }
        try:
            created = self.store.insert_job(row)
        except sqlite3.IntegrityError as e:
            if body.idempotency_key:
                existing = self.store.find_job_by_idempotency(task_id, body.idempotency_key)
                if existing:
                    return self._job_response(existing)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_public_error("idempotency_conflict", str(e)),
            ) from e
        events.emit_lifecycle_event(events.JOB_QUEUED, task_id=task_id, job_id=job_id)
        return self._job_response(created)

    def list_jobs(self, owner_user_id: str, task_id: str) -> list[JobResponse]:
        self._require_task(owner_user_id, task_id)
        return [self._job_response(j) for j in self.store.list_jobs_for_task(task_id)]

    def create_artifact(
        self, owner_user_id: str, task_id: str, body: ArtifactCreateRequest
    ) -> ArtifactResponse:
        self._require_task(owner_user_id, task_id)
        if body.run_id:
            self._require_run(owner_user_id, task_id, body.run_id)
        if body.job_id:
            self._require_job(owner_user_id, task_id, body.job_id)
        art_id = new_external_id("art")
        row = {
            "id": art_id,
            "task_id": task_id,
            "run_id": body.run_id,
            "job_id": body.job_id,
            "type": body.type,
            "name": body.name,
            "version": body.version,
            "uri": body.uri,
            "storage_backend": body.storage_backend,
            "content_type": body.content_type,
            "sha256": body.sha256,
            "size_bytes": body.size_bytes,
            "metadata": body.metadata,
            "created_by": owner_user_id,
        }
        created = self.store.insert_artifact(row)
        events.emit_lifecycle_event(events.ARTIFACT_REGISTERED, task_id=task_id, artifact_id=art_id)
        return self._artifact_response(created)

    def list_artifacts(self, owner_user_id: str, task_id: str) -> list[ArtifactResponse]:
        self._require_task(owner_user_id, task_id)
        return [self._artifact_response(a) for a in self.store.list_artifacts_for_task(task_id)]

    @staticmethod
    def _task_summary(task: dict[str, Any]) -> TaskSummaryResponse:
        return TaskSummaryResponse(
            id=task["id"],
            owner_user_id=task["owner_user_id"],
            source_session_id=task.get("source_session_id"),
            title=task.get("title") or "",
            goal=task["goal"],
            status=task["status"],
            phase=task["phase"],
            priority=task["priority"],
            risk_level=task["risk_level"],
            autonomy_mode=task["autonomy_mode"],
            current_run_id=task.get("current_run_id"),
            latest_plan_revision_id=task.get("latest_plan_revision_id"),
            created_at=task["created_at"],
            updated_at=task["updated_at"],
        )

    @staticmethod
    def _run_response(row: dict[str, Any]) -> ExperimentRunResponse:
        return ExperimentRunResponse(
            id=row["id"],
            task_id=row["task_id"],
            parent_run_id=row.get("parent_run_id"),
            run_type=row["run_type"],
            status=row["status"],
            model_name=row.get("model_name"),
            dataset_artifact_id=row.get("dataset_artifact_id"),
            model_artifact_id=row.get("model_artifact_id"),
            code_version=row.get("code_version"),
            executor_type=row.get("executor_type"),
            repro_command=row.get("repro_command"),
            config=row["config"],
            metrics=row["metrics"],
            summary=row["summary"],
            cost=row["cost"],
            failure_reason=row.get("failure_reason"),
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
        )

    @staticmethod
    def _job_response(row: dict[str, Any]) -> JobResponse:
        return JobResponse(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row.get("run_id"),
            queue_name=row["queue_name"],
            job_type=row["job_type"],
            status=row["status"],
            priority=row["priority"],
            idempotency_key=row.get("idempotency_key"),
            executor_type=row.get("executor_type"),
            payload=row["payload"],
            result=row["result"],
            checkpoint_uri=row.get("checkpoint_uri"),
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            next_attempt_at=row.get("next_attempt_at"),
            lease_owner=row.get("lease_owner"),
            lease_expires_at=row.get("lease_expires_at"),
            last_error=row.get("last_error"),
            created_by=row.get("created_by"),
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
        )

    @staticmethod
    def _artifact_response(row: dict[str, Any]) -> ArtifactResponse:
        return ArtifactResponse(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row.get("run_id"),
            job_id=row.get("job_id"),
            type=row["type"],
            name=row.get("name") or "",
            version=row.get("version"),
            uri=row["uri"],
            storage_backend=row["storage_backend"],
            content_type=row.get("content_type"),
            sha256=row.get("sha256"),
            size_bytes=row.get("size_bytes"),
            metadata=row["metadata"],
            created_by=row.get("created_by"),
            created_at=row["created_at"],
        )


_lifecycle_singleton: LifecycleService | None = None


def get_lifecycle_service() -> LifecycleService:
    global _lifecycle_singleton
    if _lifecycle_singleton is None:
        _lifecycle_singleton = LifecycleService()
    return _lifecycle_singleton


def reset_lifecycle_service_for_tests() -> None:
    """Clear process-wide singleton (unit tests only)."""
    global _lifecycle_singleton
    _lifecycle_singleton = None
