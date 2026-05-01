"""Persistent ML lifecycle state for autonomous agent workflows.

This module intentionally uses SQLite from the standard library so the web
backend can keep task / experiment / job / artifact state without introducing a
new service dependency. It is scoped by user_id and can later be swapped for
Postgres or Mongo behind the same method-level contract.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class LifecycleStore:
    """Small persistent registry for autonomous ML work.

    The schema captures the durable loop:
    task -> experiments -> jobs -> artifacts.
    """

    def __init__(self, db_path: str | None = None) -> None:
        default_path = Path(__file__).parent / ".data" / "ml_lifecycle.sqlite"
        self.db_path = Path(db_path or os.environ.get("ML_INTERN_LIFECYCLE_DB") or default_path)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lifecycle_tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    success_metrics_json TEXT NOT NULL DEFAULT '{}',
                    plan_json TEXT NOT NULL DEFAULT '[]',
                    current_phase TEXT NOT NULL DEFAULT 'intake',
                    status TEXT NOT NULL DEFAULT 'active',
                    last_decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_lifecycle_tasks_user_updated
                    ON lifecycle_tasks(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS lifecycle_experiments (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    dataset_version TEXT,
                    model_id TEXT,
                    training_config_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'planned',
                    failure_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES lifecycle_tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_lifecycle_experiments_task
                    ON lifecycle_experiments(task_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS lifecycle_jobs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    experiment_id TEXT,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    command TEXT,
                    hardware TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    logs_uri TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES lifecycle_tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(experiment_id) REFERENCES lifecycle_experiments(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_lifecycle_jobs_task
                    ON lifecycle_jobs(task_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS lifecycle_artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    experiment_id TEXT,
                    job_id TEXT,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    checksum TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES lifecycle_tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(experiment_id) REFERENCES lifecycle_experiments(id) ON DELETE SET NULL,
                    FOREIGN KEY(job_id) REFERENCES lifecycle_jobs(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_lifecycle_artifacts_task
                    ON lifecycle_artifacts(task_id, created_at DESC);
                """
            )

    def _task_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "goal": row["goal"],
            "constraints": _json_loads(row["constraints_json"], {}),
            "success_metrics": _json_loads(row["success_metrics_json"], {}),
            "plan": _json_loads(row["plan_json"], []),
            "current_phase": row["current_phase"],
            "status": row["status"],
            "last_decision": row["last_decision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _experiment_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "user_id": row["user_id"],
            "hypothesis": row["hypothesis"],
            "dataset_version": row["dataset_version"],
            "model_id": row["model_id"],
            "training_config": _json_loads(row["training_config_json"], {}),
            "metrics": _json_loads(row["metrics_json"], {}),
            "status": row["status"],
            "failure_reason": row["failure_reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _job_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "experiment_id": row["experiment_id"],
            "user_id": row["user_id"],
            "kind": row["kind"],
            "command": row["command"],
            "hardware": row["hardware"],
            "status": row["status"],
            "logs_uri": row["logs_uri"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _artifact_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "experiment_id": row["experiment_id"],
            "job_id": row["job_id"],
            "user_id": row["user_id"],
            "type": row["type"],
            "uri": row["uri"],
            "checksum": row["checksum"],
            "metadata": _json_loads(row["metadata_json"], {}),
            "created_at": row["created_at"],
        }

    def create_task(
        self,
        *,
        user_id: str,
        goal: str,
        constraints: JsonDict | None = None,
        success_metrics: JsonDict | None = None,
        plan: list[JsonDict] | None = None,
    ) -> JsonDict:
        task_id = _new_id("task")
        timestamp = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_tasks (
                    id, user_id, goal, constraints_json, success_metrics_json,
                    plan_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    user_id,
                    goal,
                    _json_dumps(constraints),
                    _json_dumps(success_metrics),
                    json.dumps(plan or [], ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_task(user_id=user_id, task_id=task_id) or {}

    def list_tasks(self, *, user_id: str) -> list[JsonDict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM lifecycle_tasks
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def get_task(self, *, user_id: str, task_id: str, include_children: bool = True) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lifecycle_tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
            if not row:
                return None
            task = self._task_from_row(row)
            if include_children:
                task["experiments"] = [
                    self._experiment_from_row(r)
                    for r in conn.execute(
                        "SELECT * FROM lifecycle_experiments WHERE task_id = ? AND user_id = ? ORDER BY created_at DESC",
                        (task_id, user_id),
                    ).fetchall()
                ]
                task["jobs"] = [
                    self._job_from_row(r)
                    for r in conn.execute(
                        "SELECT * FROM lifecycle_jobs WHERE task_id = ? AND user_id = ? ORDER BY created_at DESC",
                        (task_id, user_id),
                    ).fetchall()
                ]
                task["artifacts"] = [
                    self._artifact_from_row(r)
                    for r in conn.execute(
                        "SELECT * FROM lifecycle_artifacts WHERE task_id = ? AND user_id = ? ORDER BY created_at DESC",
                        (task_id, user_id),
                    ).fetchall()
                ]
        return task

    def update_task(self, *, user_id: str, task_id: str, updates: JsonDict) -> JsonDict | None:
        allowed = {
            "goal": "goal",
            "constraints": "constraints_json",
            "success_metrics": "success_metrics_json",
            "plan": "plan_json",
            "current_phase": "current_phase",
            "status": "status",
            "last_decision": "last_decision",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in updates:
                continue
            value = updates[key]
            if key in {"constraints", "success_metrics"}:
                value = _json_dumps(value)
            elif key == "plan":
                value = json.dumps(value or [], ensure_ascii=False)
            assignments.append(f"{column} = ?")
            values.append(value)
        if not assignments:
            return self.get_task(user_id=user_id, task_id=task_id)

        assignments.append("updated_at = ?")
        values.append(_now())
        values.extend([task_id, user_id])
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE lifecycle_tasks SET {', '.join(assignments)} WHERE id = ? AND user_id = ?",
                values,
            )
        return self.get_task(user_id=user_id, task_id=task_id)

    def create_experiment(
        self,
        *,
        user_id: str,
        task_id: str,
        hypothesis: str,
        dataset_version: str | None = None,
        model_id: str | None = None,
        training_config: JsonDict | None = None,
    ) -> JsonDict | None:
        if not self.get_task(user_id=user_id, task_id=task_id, include_children=False):
            return None
        experiment_id = _new_id("exp")
        timestamp = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_experiments (
                    id, task_id, user_id, hypothesis, dataset_version, model_id,
                    training_config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    task_id,
                    user_id,
                    hypothesis,
                    dataset_version,
                    model_id,
                    _json_dumps(training_config),
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                "UPDATE lifecycle_tasks SET current_phase = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                ("experimenting", timestamp, task_id, user_id),
            )
        return self.get_experiment(user_id=user_id, experiment_id=experiment_id)

    def get_experiment(self, *, user_id: str, experiment_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lifecycle_experiments WHERE id = ? AND user_id = ?",
                (experiment_id, user_id),
            ).fetchone()
        return self._experiment_from_row(row) if row else None

    def update_experiment(self, *, user_id: str, experiment_id: str, updates: JsonDict) -> JsonDict | None:
        allowed = {
            "hypothesis": "hypothesis",
            "dataset_version": "dataset_version",
            "model_id": "model_id",
            "training_config": "training_config_json",
            "metrics": "metrics_json",
            "status": "status",
            "failure_reason": "failure_reason",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in updates:
                continue
            value = updates[key]
            if key in {"training_config", "metrics"}:
                value = _json_dumps(value)
            assignments.append(f"{column} = ?")
            values.append(value)
        if not assignments:
            return self.get_experiment(user_id=user_id, experiment_id=experiment_id)
        assignments.append("updated_at = ?")
        values.append(_now())
        values.extend([experiment_id, user_id])
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE lifecycle_experiments SET {', '.join(assignments)} WHERE id = ? AND user_id = ?",
                values,
            )
        return self.get_experiment(user_id=user_id, experiment_id=experiment_id)

    def create_job(
        self,
        *,
        user_id: str,
        task_id: str,
        kind: str,
        experiment_id: str | None = None,
        command: str | None = None,
        hardware: str | None = None,
        status: str = "queued",
    ) -> JsonDict | None:
        if not self.get_task(user_id=user_id, task_id=task_id, include_children=False):
            return None
        job_id = _new_id("job")
        timestamp = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_jobs (
                    id, task_id, experiment_id, user_id, kind, command, hardware,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, task_id, experiment_id, user_id, kind, command, hardware, status, timestamp, timestamp),
            )
            conn.execute(
                "UPDATE lifecycle_tasks SET updated_at = ? WHERE id = ? AND user_id = ?",
                (timestamp, task_id, user_id),
            )
        return self.get_job(user_id=user_id, job_id=job_id)

    def get_job(self, *, user_id: str, job_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lifecycle_jobs WHERE id = ? AND user_id = ?",
                (job_id, user_id),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def update_job(self, *, user_id: str, job_id: str, updates: JsonDict) -> JsonDict | None:
        allowed = {
            "kind": "kind",
            "command": "command",
            "hardware": "hardware",
            "status": "status",
            "logs_uri": "logs_uri",
            "error": "error",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key in updates:
                assignments.append(f"{column} = ?")
                values.append(updates[key])
        if not assignments:
            return self.get_job(user_id=user_id, job_id=job_id)
        assignments.append("updated_at = ?")
        values.append(_now())
        values.extend([job_id, user_id])
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE lifecycle_jobs SET {', '.join(assignments)} WHERE id = ? AND user_id = ?",
                values,
            )
        return self.get_job(user_id=user_id, job_id=job_id)

    def create_artifact(
        self,
        *,
        user_id: str,
        task_id: str,
        type: str,
        uri: str,
        experiment_id: str | None = None,
        job_id: str | None = None,
        checksum: str | None = None,
        metadata: JsonDict | None = None,
    ) -> JsonDict | None:
        if not self.get_task(user_id=user_id, task_id=task_id, include_children=False):
            return None
        artifact_id = _new_id("art")
        timestamp = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lifecycle_artifacts (
                    id, task_id, experiment_id, job_id, user_id, type, uri,
                    checksum, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    task_id,
                    experiment_id,
                    job_id,
                    user_id,
                    type,
                    uri,
                    checksum,
                    _json_dumps(metadata),
                    timestamp,
                ),
            )
            conn.execute(
                "UPDATE lifecycle_tasks SET current_phase = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                ("artifact_review", timestamp, task_id, user_id),
            )
            row = conn.execute(
                "SELECT * FROM lifecycle_artifacts WHERE id = ? AND user_id = ?",
                (artifact_id, user_id),
            ).fetchone()
        return self._artifact_from_row(row) if row else None


lifecycle_store = LifecycleStore()
