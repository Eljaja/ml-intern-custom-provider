from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.context_manager.manager import ContextManager
from agent.core import skills
from agent.core.agent_loop import _maybe_reflect_skill
from agent.tools.skills_tool import skill_manage_handler, skill_view_handler


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


def test_skill_rejects_invalid_names_and_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    with pytest.raises(skills.SkillError):
        skills.upsert_skill(
            "user",
            name="../escape",
            description="bad",
            content="nope",
        )

    skill = skills.upsert_skill(
        "user",
        name="safe-skill",
        description="safe",
        content="Use token hf_abcdefghijklmnopqrstuvwxyz123456 carefully.",
    )
    assert "hf_abcdefghijklmnopqrstuvwxyz123456" not in skill.content
    assert "[REDACTED]" in skill.content


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


@pytest.mark.asyncio
async def test_skill_reflection_can_create_skill(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    class FakeChoice:
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
        local_mode=False,
        user_id="user",
        logged_events=events,
        context_manager=SimpleNamespace(
            items=[
                SimpleNamespace(role="user", content="Do a reusable workflow"),
                SimpleNamespace(role="assistant", content="Done"),
            ]
        ),
        config=SimpleNamespace(model_name="test-model"),
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

    await _maybe_reflect_skill(session, event_start_idx=0, errored=False)

    created = skills.get_skill("user", "auto-skill")
    assert created is not None
    assert "Repeat this workflow" in created.content
    assert sent_events and sent_events[0].event_type == "skills_updated"
