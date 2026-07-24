"""Idle-session reaper.

See the REAPER_* block in backend/session_manager.py. Nothing ever left
self.sessions before this: forgotten runtimes held their memory and sandbox until
the process restarted, and the pool filled up until create started failing with
"Server is at capacity".
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import session_manager as sm  # noqa: E402


def _agent_session(
    manager,
    session_id="s1",
    *,
    idle_minutes=999,
    is_processing=False,
    pending_approval=None,
    queue_items=0,
):
    queue: asyncio.Queue = asyncio.Queue()
    for i in range(queue_items):
        queue.put_nowait(f"pending-{i}")

    task = SimpleNamespace(done=lambda: True, cancel=lambda: None)
    agent_session = sm.AgentSession(
        session_id=session_id,
        session=SimpleNamespace(
            pending_approval=pending_approval,
            config=SimpleNamespace(model_name="m"),
            turn_count=1,
            notification_destinations=[],
            sandbox=None,
        ),
        tool_router=SimpleNamespace(),
        submission_queue=queue,
        user_id="alice",
        task=task,
    )
    agent_session.last_active_at = datetime.utcnow() - timedelta(minutes=idle_minutes)
    agent_session.is_processing = is_processing
    manager.sessions[session_id] = agent_session
    return agent_session


@pytest.fixture
def manager(monkeypatch):
    """A SessionManager with persistence and sandbox teardown stubbed out."""
    mgr = sm.SessionManager.__new__(sm.SessionManager)
    mgr.sessions = {}
    mgr._lock = asyncio.Lock()
    mgr._reaper_task = None
    mgr.persistence_store = SimpleNamespace(enabled=True)

    snapshots = []

    async def persist(agent_session, **kwargs):
        snapshots.append((agent_session.session_id, kwargs))

    async def cleanup_sandbox(_session):
        return None

    monkeypatch.setattr(mgr, "persist_session_snapshot", persist, raising=False)
    monkeypatch.setattr(mgr, "_cleanup_sandbox", cleanup_sandbox, raising=False)
    monkeypatch.setattr(mgr, "_store", lambda: mgr.persistence_store, raising=False)
    mgr.snapshots = snapshots
    return mgr


# ── what gets reaped ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_idle_session_is_evicted_but_stays_resumable(manager):
    _agent_session(manager, "idle-1")

    assert await manager._reap_idle_sessions() == 1
    assert "idle-1" not in manager.sessions

    # status must be "active", never "ended" — it has to come back as a normal chat.
    _, kwargs = manager.snapshots[-1]
    assert kwargs["status"] == "active"
    assert kwargs["runtime_state"] == "idle"
    assert kwargs["raise_on_error"] is True


@pytest.mark.asyncio
async def test_recently_active_session_is_spared(manager):
    _agent_session(manager, "fresh", idle_minutes=0)
    assert await manager._reap_idle_sessions() == 0
    assert "fresh" in manager.sessions


@pytest.mark.asyncio
async def test_processing_session_is_spared(manager):
    _agent_session(manager, "busy", is_processing=True)
    assert await manager._reap_idle_sessions() == 0
    assert "busy" in manager.sessions


@pytest.mark.asyncio
async def test_session_awaiting_approval_is_spared(manager):
    """Approve-later is not idle: reaping would destroy the sandbox it needs."""
    _agent_session(manager, "waiting", pending_approval={"tool": "bash"})
    assert await manager._reap_idle_sessions() == 0
    assert "waiting" in manager.sessions


@pytest.mark.asyncio
async def test_session_with_queued_work_is_spared(manager):
    _agent_session(manager, "queued", queue_items=1)
    assert await manager._reap_idle_sessions() == 0
    assert "queued" in manager.sessions


@pytest.mark.asyncio
async def test_reaping_is_skipped_entirely_without_a_store(manager):
    """With no persistence, eviction would destroy the conversation."""
    manager.persistence_store = SimpleNamespace(enabled=False)
    _agent_session(manager, "no-store")
    assert await manager._reap_idle_sessions() == 0
    assert "no-store" in manager.sessions


@pytest.mark.asyncio
async def test_reap_aborts_when_the_snapshot_cannot_be_written(manager, monkeypatch):
    async def failing_persist(_agent_session, **_kwargs):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(manager, "persist_session_snapshot", failing_persist)
    agent_session = _agent_session(manager, "unwritable")

    assert await manager._reap_idle_sessions() == 0
    assert "unwritable" in manager.sessions
    assert agent_session.is_reaping is False, "must be cleared so a later sweep retries"


@pytest.mark.asyncio
async def test_multiple_idle_sessions_are_all_reaped(manager):
    for i in range(3):
        _agent_session(manager, f"idle-{i}")
    assert await manager._reap_idle_sessions() == 3
    assert manager.sessions == {}


# ── the submit/reap race ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_is_refused_while_a_session_is_being_reaped(manager):
    agent_session = _agent_session(manager, "racing")
    agent_session.is_reaping = True

    ok = await sm.SessionManager.submit(
        manager,
        "racing",
        sm.Operation(op_type=sm.OpType.USER_INPUT, data={"text": "x"}),
    )
    assert ok is False
    assert agent_session.submission_queue.empty()


@pytest.mark.asyncio
async def test_submit_resets_the_idle_clock(manager):
    agent_session = _agent_session(manager, "reset-me")
    before = agent_session.last_active_at

    ok = await sm.SessionManager.submit(
        manager,
        "reset-me",
        sm.Operation(op_type=sm.OpType.USER_INPUT, data={"text": "x"}),
    )
    assert ok is True
    assert agent_session.last_active_at > before
    assert agent_session.submission_queue.qsize() == 1


@pytest.mark.asyncio
async def test_a_session_that_becomes_active_mid_reap_is_not_evicted(
    manager, monkeypatch
):
    """The user typed while the snapshot write was in flight."""
    agent_session = _agent_session(manager, "revived")

    async def persist_then_activate(session, **_kwargs):
        # Simulate work arriving during the (awaited) Mongo write.
        session.submission_queue.put_nowait("late-arrival")

    monkeypatch.setattr(manager, "persist_session_snapshot", persist_then_activate)

    assert await manager._reap_idle_sessions() == 0
    assert "revived" in manager.sessions
    assert agent_session.is_reaping is False


@pytest.mark.asyncio
async def test_touch_activity_is_a_noop_for_a_missing_session():
    sm.SessionManager.touch_activity(None)  # must not raise


# ── loop lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reaper_loop_survives_a_failing_sweep(manager, monkeypatch):
    calls = []

    async def boom():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient")

    monkeypatch.setattr(manager, "_reap_idle_sessions", boom)
    monkeypatch.setattr(sm, "REAPER_INTERVAL_S", 0.001)

    task = asyncio.create_task(sm.SessionManager._reaper_loop(manager))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2, "a failed sweep must not kill the loop"
