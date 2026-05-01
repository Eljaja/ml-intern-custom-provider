"""SQLite persistence for lifecycle entities."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class LifecycleStore:
    """Thread-safe SQLite store; Postgres-ready schema shape."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        env_path = os.environ.get("ML_INTERN_LIFECYCLE_DB")
        if db_path is not None:
            self.db_path = Path(db_path)
        elif env_path:
            self.db_path = Path(env_path)
        else:
            self.db_path = Path(__file__).resolve().parent.parent / ".data" / "ml_lifecycle.sqlite"
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    source_session_id TEXT,
                    title TEXT NOT NULL DEFAULT '',
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    autonomy_mode TEXT NOT NULL DEFAULT 'supervised',
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    acceptance_json TEXT NOT NULL DEFAULT '{}',
                    current_run_id TEXT,
                    latest_plan_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_owner_updated
                    ON tasks(owner_user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS plan_revisions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    revision_index INTEGER NOT NULL,
                    summary TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_plan_revisions_task
                    ON plan_revisions(task_id, revision_index DESC);

                CREATE TABLE IF NOT EXISTS plan_steps (
                    id TEXT PRIMARY KEY,
                    plan_revision_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(plan_revision_id) REFERENCES plan_revisions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS experiment_runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    parent_run_id TEXT,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model_name TEXT,
                    dataset_artifact_id TEXT,
                    model_artifact_id TEXT,
                    code_version TEXT,
                    executor_type TEXT,
                    repro_command TEXT,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    cost_json TEXT NOT NULL DEFAULT '{}',
                    failure_reason TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_runs_task
                    ON experiment_runs(task_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    run_id TEXT,
                    queue_name TEXT NOT NULL DEFAULT 'default',
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT,
                    executor_type TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_uri TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_attempt_at TEXT,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_task ON jobs(task_id, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency
                    ON jobs(task_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS job_attempts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    run_id TEXT,
                    job_id TEXT,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    version TEXT,
                    uri TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local_file',
                    content_type TEXT,
                    sha256 TEXT,
                    size_bytes INTEGER,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_task
                    ON artifacts(task_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    run_id TEXT,
                    job_id TEXT,
                    approval_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    title TEXT,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    decided_by TEXT,
                    decided_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS evaluation_gate_results (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    gate_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    score_json TEXT NOT NULL DEFAULT '{}',
                    threshold_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    evaluated_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                """
            )

    # --- tasks ----------------------------------------------------------------

    def insert_task(self, row: JsonDict) -> JsonDict:
        now = _utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, owner_user_id, source_session_id, title, goal, status, phase,
                    priority, risk_level, autonomy_mode, constraints_json, acceptance_json,
                    current_run_id, latest_plan_revision_id, created_at, updated_at,
                    started_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["id"],
                    row["owner_user_id"],
                    row.get("source_session_id"),
                    row.get("title", ""),
                    row["goal"],
                    row["status"],
                    row["phase"],
                    int(row.get("priority", 0)),
                    row.get("risk_level", "medium"),
                    row.get("autonomy_mode", "supervised"),
                    _json_dumps(row.get("constraints", {})),
                    _json_dumps(row.get("acceptance", {})),
                    row.get("current_run_id"),
                    row.get("latest_plan_revision_id"),
                    row.get("created_at", now),
                    row.get("updated_at", now),
                    row.get("started_at"),
                    row.get("finished_at"),
                ),
            )
            conn.commit()
        return self.get_task_by_id(row["id"])

    def get_task_by_id(self, task_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            r = cur.fetchone()
        return None if r is None else self._task_from_row(r)

    def list_tasks_for_owner(self, owner_user_id: str, *, limit: int = 200) -> list[JsonDict]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM tasks WHERE owner_user_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (owner_user_id, limit),
            )
            rows = cur.fetchall()
        return [self._task_from_row(r) for r in rows]

    def update_task(self, task_id: str, updates: JsonDict) -> JsonDict | None:
        existing = self.get_task_by_id(task_id)
        if not existing:
            return None
        now = _utc_now_iso()
        fields: list[str] = []
        values: list[Any] = []
        mapping = {
            "source_session_id": "source_session_id",
            "title": "title",
            "goal": "goal",
            "status": "status",
            "phase": "phase",
            "priority": "priority",
            "risk_level": "risk_level",
            "autonomy_mode": "autonomy_mode",
            "constraints_json": None,
            "acceptance_json": None,
            "current_run_id": "current_run_id",
            "latest_plan_revision_id": "latest_plan_revision_id",
            "started_at": "started_at",
            "finished_at": "finished_at",
        }
        for key, col in mapping.items():
            if key not in updates:
                continue
            if col is None:
                continue
            fields.append(f"{col} = ?")
            values.append(updates[key])
        if "constraints" in updates:
            fields.append("constraints_json = ?")
            values.append(_json_dumps(updates["constraints"]))
        if "acceptance" in updates:
            fields.append("acceptance_json = ?")
            values.append(_json_dumps(updates["acceptance"]))
        fields.append("updated_at = ?")
        values.append(now)
        values.append(task_id)
        if len(fields) == 1:  # only updated_at
            return existing
        sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"
        with self._lock, self._connect() as conn:
            conn.execute(sql, values)
            conn.commit()
        return self.get_task_by_id(task_id)

    def _task_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "owner_user_id": row["owner_user_id"],
            "source_session_id": row["source_session_id"],
            "title": row["title"] or "",
            "goal": row["goal"],
            "status": row["status"],
            "phase": row["phase"],
            "priority": row["priority"],
            "risk_level": row["risk_level"],
            "autonomy_mode": row["autonomy_mode"],
            "constraints": _json_loads(row["constraints_json"], {}),
            "acceptance": _json_loads(row["acceptance_json"], {}),
            "current_run_id": row["current_run_id"],
            "latest_plan_revision_id": row["latest_plan_revision_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    # --- runs -----------------------------------------------------------------

    def insert_run(self, row: JsonDict) -> JsonDict:
        now = _utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO experiment_runs (
                    id, task_id, parent_run_id, run_type, status, model_name,
                    dataset_artifact_id, model_artifact_id, code_version,
                    executor_type, repro_command, config_json, metrics_json,
                    summary_json, cost_json, failure_reason,
                    created_at, started_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["id"],
                    row["task_id"],
                    row.get("parent_run_id"),
                    row["run_type"],
                    row["status"],
                    row.get("model_name"),
                    row.get("dataset_artifact_id"),
                    row.get("model_artifact_id"),
                    row.get("code_version"),
                    row.get("executor_type"),
                    row.get("repro_command"),
                    _json_dumps(row.get("config", {})),
                    _json_dumps(row.get("metrics", {})),
                    _json_dumps(row.get("summary", {})),
                    _json_dumps(row.get("cost", {})),
                    row.get("failure_reason"),
                    row.get("created_at", now),
                    row.get("started_at"),
                    row.get("finished_at"),
                ),
            )
            conn.commit()
        return self.get_run_by_id(row["id"])

    def get_run_by_id(self, run_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM experiment_runs WHERE id = ?", (run_id,))
            r = cur.fetchone()
        return None if r is None else self._run_from_row(r)

    def list_runs_for_task(self, task_id: str) -> list[JsonDict]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM experiment_runs WHERE task_id = ?
                ORDER BY created_at ASC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        return [self._run_from_row(r) for r in rows]

    def _run_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "parent_run_id": row["parent_run_id"],
            "run_type": row["run_type"],
            "status": row["status"],
            "model_name": row["model_name"],
            "dataset_artifact_id": row["dataset_artifact_id"],
            "model_artifact_id": row["model_artifact_id"],
            "code_version": row["code_version"],
            "executor_type": row["executor_type"],
            "repro_command": row["repro_command"],
            "config": _json_loads(row["config_json"], {}),
            "metrics": _json_loads(row["metrics_json"], {}),
            "summary": _json_loads(row["summary_json"], {}),
            "cost": _json_loads(row["cost_json"], {}),
            "failure_reason": row["failure_reason"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    # --- jobs -----------------------------------------------------------------

    def find_job_by_idempotency(self, task_id: str, key: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM jobs WHERE task_id = ? AND idempotency_key = ?",
                (task_id, key),
            )
            r = cur.fetchone()
        return None if r is None else self._job_from_row(r)

    def insert_job(self, row: JsonDict) -> JsonDict:
        now = _utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, task_id, run_id, queue_name, job_type, status, priority,
                    idempotency_key, executor_type, payload_json, result_json,
                    checkpoint_uri, attempt_count, max_attempts, next_attempt_at,
                    lease_owner, lease_expires_at, last_error, created_by,
                    created_at, started_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["id"],
                    row["task_id"],
                    row.get("run_id"),
                    row.get("queue_name", "default"),
                    row["job_type"],
                    row["status"],
                    int(row.get("priority", 0)),
                    row.get("idempotency_key"),
                    row.get("executor_type"),
                    _json_dumps(row.get("payload", {})),
                    _json_dumps(row.get("result", {})),
                    row.get("checkpoint_uri"),
                    int(row.get("attempt_count", 0)),
                    int(row.get("max_attempts", 3)),
                    row.get("next_attempt_at"),
                    row.get("lease_owner"),
                    row.get("lease_expires_at"),
                    row.get("last_error"),
                    row.get("created_by"),
                    row.get("created_at", now),
                    row.get("started_at"),
                    row.get("finished_at"),
                ),
            )
            conn.commit()
        return self.get_job_by_id(row["id"])

    def get_job_by_id(self, job_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            r = cur.fetchone()
        return None if r is None else self._job_from_row(r)

    def list_jobs_for_task(self, task_id: str) -> list[JsonDict]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM jobs WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            )
            rows = cur.fetchall()
        return [self._job_from_row(r) for r in rows]

    def _job_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "run_id": row["run_id"],
            "queue_name": row["queue_name"],
            "job_type": row["job_type"],
            "status": row["status"],
            "priority": row["priority"],
            "idempotency_key": row["idempotency_key"],
            "executor_type": row["executor_type"],
            "payload": _json_loads(row["payload_json"], {}),
            "result": _json_loads(row["result_json"], {}),
            "checkpoint_uri": row["checkpoint_uri"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "next_attempt_at": row["next_attempt_at"],
            "lease_owner": row["lease_owner"],
            "lease_expires_at": row["lease_expires_at"],
            "last_error": row["last_error"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    # --- artifacts ------------------------------------------------------------

    def insert_artifact(self, row: JsonDict) -> JsonDict:
        now = _utc_now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, task_id, run_id, job_id, type, name, version, uri,
                    storage_backend, content_type, sha256, size_bytes,
                    metadata_json, created_by, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["id"],
                    row["task_id"],
                    row.get("run_id"),
                    row.get("job_id"),
                    row["type"],
                    row.get("name", ""),
                    row.get("version"),
                    row["uri"],
                    row.get("storage_backend", "local_file"),
                    row.get("content_type"),
                    row.get("sha256"),
                    row.get("size_bytes"),
                    _json_dumps(row.get("metadata", {})),
                    row.get("created_by"),
                    row.get("created_at", now),
                ),
            )
            conn.commit()
        return self.get_artifact_by_id(row["id"])

    def get_artifact_by_id(self, artifact_id: str) -> JsonDict | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            r = cur.fetchone()
        return None if r is None else self._artifact_from_row(r)

    def list_artifacts_for_task(self, task_id: str) -> list[JsonDict]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            )
            rows = cur.fetchall()
        return [self._artifact_from_row(r) for r in rows]

    def _artifact_from_row(self, row: sqlite3.Row) -> JsonDict:
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "run_id": row["run_id"],
            "job_id": row["job_id"],
            "type": row["type"],
            "name": row["name"] or "",
            "version": row["version"],
            "uri": row["uri"],
            "storage_backend": row["storage_backend"],
            "content_type": row["content_type"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "metadata": _json_loads(row["metadata_json"], {}),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
        }
