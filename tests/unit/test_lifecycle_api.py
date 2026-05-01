"""Lifecycle v2 API: durable tasks, runs, jobs, artifacts."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from lifecycle.service import LifecycleService
from lifecycle.store import LifecycleStore
from routes.lifecycle import get_lifecycle_dep


@pytest.fixture
def lifecycle_client(tmp_path, monkeypatch):
    monkeypatch.delenv("OAUTH_CLIENT_ID", raising=False)
    db_path = tmp_path / "lc.sqlite"
    store = LifecycleStore(db_path)
    svc = LifecycleService(store)

    import main

    importlib.reload(main)
    main.app.dependency_overrides[get_lifecycle_dep] = lambda: svc
    with TestClient(main.app) as client:
        yield client, db_path, store
    main.app.dependency_overrides.pop(get_lifecycle_dep, None)


def test_lifecycle_persists_across_restart(lifecycle_client):
    client, db_path, _store = lifecycle_client

    r = client.post("/api/v2/tasks", json={"goal": "Train a classifier", "title": "demo"})
    assert r.status_code == 200, r.text
    task_id = r.json()["id"]
    assert task_id.startswith("tsk_")

    r2 = client.post(
        f"/api/v2/tasks/{task_id}/runs",
        json={"run_type": "training", "config": {"lr": 0.01}},
    )
    assert r2.status_code == 200, r2.text
    run_id = r2.json()["id"]
    assert run_id.startswith("run_")

    r3 = client.post(
        f"/api/v2/tasks/{task_id}/jobs",
        json={"job_type": "plan", "payload": {"step": 1}},
    )
    assert r3.status_code == 200, r3.text
    job_id = r3.json()["id"]
    assert job_id.startswith("job_")

    r4 = client.post(
        f"/api/v2/tasks/{task_id}/artifacts",
        json={"type": "metrics", "uri": "file:///tmp/metrics.json", "run_id": run_id},
    )
    assert r4.status_code == 200, r4.text
    assert r4.json()["id"].startswith("art_")

    detail = client.get(f"/api/v2/tasks/{task_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert len(body["runs"]) == 1
    assert len(body["jobs"]) == 1
    assert len(body["artifacts"]) == 1

    store2 = LifecycleStore(db_path)
    task = store2.get_task_by_id(task_id)
    assert task is not None
    assert task["goal"] == "Train a classifier"
    assert len(store2.list_runs_for_task(task_id)) == 1
    assert len(store2.list_jobs_for_task(task_id)) == 1
    assert len(store2.list_artifacts_for_task(task_id)) == 1


def test_task_forbidden_for_other_user(lifecycle_client):
    client, _db, _store = lifecycle_client

    r = client.post("/api/v2/tasks", json={"goal": "secret"})
    task_id = r.json()["id"]

    import main
    from dependencies import DEV_USER, get_current_user

    async def other_user():
        return {**DEV_USER, "user_id": "user-b"}

    main.app.dependency_overrides[get_current_user] = other_user
    try:
        blocked = client.get(f"/api/v2/tasks/{task_id}")
        assert blocked.status_code == 403
    finally:
        main.app.dependency_overrides.pop(get_current_user, None)


def test_existing_chat_routes_still_exist(lifecycle_client):
    client, _, _ = lifecycle_client
    h = client.get("/api/health")
    assert h.status_code == 200
