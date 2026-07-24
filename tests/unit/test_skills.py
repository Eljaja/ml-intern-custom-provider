from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.context_manager.manager import ContextManager
from agent.core import skills
from agent.core.agent_loop import _maybe_reflect_skill
from agent.tools.skills_tool import skill_manage_handler, skill_view_handler
from backend.models import SkillSummary


def test_skill_create_patch_toggle_and_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    created = skills.upsert_skill(
        "user/one",
        name="train-recipe",
        description="Reusable training recipe",
        content="# Procedure\nRun docs first.",
    )
    assert created.enabled is True
    assert (tmp_path / "user_one" / "train-recipe" / "SKILL.md").exists()

    assert skills.get_skill("other", "train-recipe") is None

    patched = skills.patch_skill(
        "user/one",
        name="train-recipe",
        old_string="Run docs first.",
        new_string="Run research and docs first.",
    )
    assert "research and docs" in patched.content

    disabled = skills.set_skill_enabled("user/one", "train-recipe", False)
    assert disabled.enabled is False
    assert skills.get_skill("user/one", "train-recipe", require_enabled=True) is None


def test_skill_frontmatter_dates_are_api_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    skill_dir = tmp_path / "dev" / "dated-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: dated-skill\n"
        "description: dated\n"
        "created_at: 2026-01-01\n"
        "updated_at: 2026-01-02\n"
        "last_used_at: 2026-06-03\n"
        "use_count: 1\n"
        "---\n\n"
        "Procedure body.\n",
        encoding="utf-8",
    )

    skill = skills.get_skill("dev", "dated-skill")
    assert skill is not None
    summary = SkillSummary(**skill.summary())
    assert summary.last_used_at is not None
    assert "2026-06-03" in summary.last_used_at


def test_migrate_dev_skills_into_hf_user(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    dev_dir = tmp_path / "dev" / "workflow"
    dev_dir.mkdir(parents=True)
    (dev_dir / "SKILL.md").write_text(
        "---\nname: workflow\ndescription: dev skill\n---\n\nBody.\n",
        encoding="utf-8",
    )

    moved = skills.migrate_dev_skills_if_needed("alice")
    assert moved == 1
    assert not dev_dir.exists()
    assert (tmp_path / "alice" / "workflow" / "SKILL.md").exists()
    assert skills.list_skills("alice")[0].name == "workflow"


def test_legacy_skill_folder_with_dots_is_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    skill_dir = tmp_path / "dev" / "skills.md"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: skills.md\n"
        "description: legacy folder\n"
        "---\n\n"
        "Keep this workflow.\n",
        encoding="utf-8",
    )

    loaded = skills.list_skills("dev")
    assert len(loaded) == 1
    assert loaded[0].name == "skills-md"


def test_skill_rejects_invalid_names_and_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    with pytest.raises(skills.SkillError):
        skills.upsert_skill(
            "user",
            name="../escape",
            description="bad",
            content="nope",
        )

    # Redaction now delegates to agent.core.redact, which uses typed
    # placeholders ([REDACTED_HF_TOKEN]) rather than a bare [REDACTED].
    skill = skills.upsert_skill(
        "user",
        name="safe-skill",
        description="safe",
        content="Use token hf_abcdefghijklmnopqrstuvwxyz123456 carefully.",
    )
    assert "hf_abcdefghijklmnopqrstuvwxyz123456" not in skill.content
    assert "REDACTED" in skill.content


def test_skill_redaction_covers_credentials_the_old_local_patterns_missed(
    tmp_path, monkeypatch
):
    """The removed in-module patterns had no GitHub/AWS/Bearer coverage."""
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    secrets = {
        "github": "ghp_" + "a" * 36,
        "aws": "AKIA" + "B" * 16,
        "bearer": "Bearer " + "c" * 24,
        "zulip": "ZULIP_API_KEY=zzzzzzzzzzzzzzzzzzzz",
    }
    skill = skills.upsert_skill(
        "user",
        name="leaky",
        description="d",
        content="\n".join(secrets.values()),
    )
    for label, value in secrets.items():
        assert value not in skill.content, label
    assert "ZULIP_API_KEY=" in skill.content, "variable name should survive"


@pytest.mark.asyncio
async def test_skill_tools_scope_to_session_user(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    session = SimpleNamespace(user_id="owner", refresh_system_prompt=lambda: None)

    output, ok = await skill_manage_handler(
        {
            "action": "create",
            "name": "workflow",
            "description": "Owner workflow",
            "content": "# Workflow\nDo the thing.",
        },
        session=session,
    )
    assert ok, output

    output, ok = await skill_view_handler({"name": "workflow"}, session=session)
    assert ok, output
    assert "Do the thing" in output

    other_output, other_ok = await skill_view_handler(
        {"name": "workflow"}, session=SimpleNamespace(user_id="other")
    )
    assert not other_ok
    assert "not found" in other_output


def test_context_manager_includes_enabled_skill_index(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    skills.upsert_skill(
        "user",
        name="enabled-skill",
        description="Visible skill",
        content="Use me.",
    )
    skills.upsert_skill(
        "user",
        name="disabled-skill",
        description="Hidden skill",
        content="Do not use me.",
        enabled=False,
    )

    manager = ContextManager(
        tool_specs=[],
        hf_token=None,
        local_mode=False,
        user_id="user",
    )
    assert "enabled-skill: Visible skill" in manager.system_prompt
    assert "disabled-skill" not in manager.system_prompt

    local_web_manager = ContextManager(
        tool_specs=[],
        hf_token=None,
        local_mode=True,
        user_id="user",
    )
    assert "enabled-skill: Visible skill" in local_web_manager.system_prompt
    assert "disabled-skill" not in local_web_manager.system_prompt


@pytest.mark.asyncio
async def test_skill_reflection_can_create_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    class FakeChoice:
        finish_reason = "stop"
        message = SimpleNamespace(
            content=(
                '{"action":"create","name":"auto-skill",'
                '"description":"Auto learned workflow",'
                '"content":"# Procedure\\nRepeat this workflow."}'
            )
        )

    async def fake_acompletion(**_kwargs):
        return SimpleNamespace(choices=[FakeChoice()])

    class FakeEnv:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    events = [
        {"event_type": "tool_output", "data": {"tool": "web_search", "success": True}},
        {
            "event_type": "tool_output",
            "data": {"tool": "hf_inspect_dataset", "success": True},
        },
    ]
    sent_events = []

    async def send_event(event):
        sent_events.append(event)

    session = SimpleNamespace(
        pending_approval=None,
        is_cancelled=False,
        local_mode=True,
        user_id="user",
        logged_events=events,
        context_manager=SimpleNamespace(
            items=[
                SimpleNamespace(role="user", content="Do a reusable workflow"),
                SimpleNamespace(role="assistant", content="Done"),
            ]
        ),
        config=SimpleNamespace(model_name="test-model", skill_reflection=True),
        hf_token=None,
        effective_effort_for=lambda _model: None,
        refresh_system_prompt=lambda: None,
        send_event=send_event,
    )

    monkeypatch.setattr("agent.core.agent_loop.acompletion", fake_acompletion)
    monkeypatch.setattr(
        "agent.core.agent_loop._resolve_llm_params",
        lambda *_args, **_kwargs: {"model": "test-model"},
    )
    monkeypatch.setattr(
        "agent.core.agent_loop.use_custom_inference_openai_key_env",
        lambda *_args, **_kwargs: FakeEnv(),
    )

    await _maybe_reflect_skill(session, event_start_idx=0)

    created = skills.get_skill("user", "auto-skill")
    assert created is not None
    assert "Repeat this workflow" in created.content

    by_type = {e.event_type: e for e in sent_events}
    assert "skills_updated" in by_type

    # The reflection call must be attributed, or its spend stays invisible to
    # KPIs and to the session's total_cost_usd.
    assert "llm_call" in by_type
    assert by_type["llm_call"].data["kind"] == "skill_reflection"


def test_reflection_json_parser_tolerates_markdown_fences():
    """The system prompt forbids fences; models emit them anyway."""
    from agent.core.agent_loop import _parse_reflection_json

    assert _parse_reflection_json('{"action":"noop"}') == {"action": "noop"}
    assert _parse_reflection_json('```json\n{"action":"noop"}\n```') == {
        "action": "noop"
    }
    assert _parse_reflection_json('```\n{"action":"noop"}\n```') == {"action": "noop"}
    assert _parse_reflection_json('Sure!\n{"action":"noop"}\nHope that helps.') == {
        "action": "noop"
    }
    assert _parse_reflection_json("") is None
    assert _parse_reflection_json("not json at all") is None
    assert _parse_reflection_json('["a", "b"]') is None


def test_reflection_context_is_scrubbed_before_leaving_the_process(monkeypatch):
    """Tool output in the prompt can contain env dumps and pasted tokens."""
    from agent.core.agent_loop import _recent_messages_for_skill_reflection

    token = "hf_" + "q" * 34
    session = SimpleNamespace(
        context_manager=SimpleNamespace(
            items=[
                SimpleNamespace(role="tool", name="bash", content=f"HF_TOKEN={token}"),
                SimpleNamespace(role="assistant", content=f"I saw {token}"),
            ]
        )
    )
    rendered = _recent_messages_for_skill_reflection(session)
    assert token not in rendered
    assert "REDACTED" in rendered


@pytest.mark.asyncio
async def test_reflection_can_be_disabled_via_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    called = False

    async def fail_acompletion(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("reflection must not call the model when disabled")

    monkeypatch.setattr("agent.core.agent_loop.acompletion", fail_acompletion)

    session = SimpleNamespace(
        pending_approval=None,
        is_cancelled=False,
        user_id="user",
        logged_events=[
            {"event_type": "tool_output", "data": {"tool": "a", "success": True}},
            {"event_type": "tool_output", "data": {"tool": "b", "success": True}},
        ],
        config=SimpleNamespace(model_name="m", skill_reflection=False),
    )

    await _maybe_reflect_skill(session, event_start_idx=0)
    assert called is False


def test_skill_reflection_enabled_defaults_to_true_for_legacy_configs():
    """Restored sessions may carry a config object without the new field."""
    from agent.core.agent_loop import skill_reflection_enabled

    assert skill_reflection_enabled(SimpleNamespace()) is True
    assert skill_reflection_enabled(SimpleNamespace(skill_reflection=False)) is False


@pytest.mark.asyncio
async def test_spawn_background_task_keeps_a_strong_reference():
    """asyncio only weakly references running tasks; a bare create_task can be GC'd."""
    import asyncio
    import gc

    from agent.core.session import Session

    session = SimpleNamespace(_background_tasks=set())
    started = asyncio.Event()
    finished = []

    async def work():
        started.set()
        await asyncio.sleep(0.01)
        finished.append(True)

    task = Session.spawn_background_task(session, work(), name="t")
    await started.wait()
    gc.collect()
    assert session._background_tasks == {task}

    await Session.drain_background_tasks(session)
    assert finished == [True]
    assert session._background_tasks == set()


@pytest.mark.asyncio
async def test_drain_background_tasks_cancels_what_overruns():
    import asyncio

    from agent.core.session import Session

    session = SimpleNamespace(_background_tasks=set())

    async def forever():
        await asyncio.sleep(3600)

    task = Session.spawn_background_task(session, forever(), name="slow")
    await Session.drain_background_tasks(session, timeout=0.01)
    assert task.cancelled()


def test_spawn_background_task_without_a_loop_closes_the_coroutine():
    """CLI sync paths have no running loop; the coro must not leak un-awaited."""
    from agent.core.session import Session

    session = SimpleNamespace(_background_tasks=set())

    async def work():
        return None

    coro = work()
    assert Session.spawn_background_task(session, coro) is None
    # Closed, so awaiting it now raises rather than emitting "never awaited".
    with pytest.raises(RuntimeError):
        coro.send(None)
