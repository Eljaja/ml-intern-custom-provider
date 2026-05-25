import pytest

from types import SimpleNamespace
from pathlib import Path

from agent.core.agent_loop import _needs_approval
from agent.core.tools import create_builtin_tools
from agent.tools.sandbox_tool import get_sandbox_tools


def test_sandbox_create_requires_approval():
    config = SimpleNamespace(yolo_mode=False)

    assert _needs_approval("sandbox_create", {}, config) is True
    assert (
        _needs_approval("sandbox_create", {"hardware": "cpu-basic"}, config) is True
    )
    assert (
        _needs_approval("sandbox_create", {"hardware": "t4-small"}, config) is True
    )


def test_prompt_and_tool_specs_use_explicit_sandbox_workflow():
    prompt = Path("agent/prompts/system_prompt_v3.yaml").read_text()
    tool_specs = {tool.name: tool.description for tool in get_sandbox_tools()}

    assert "sandbox_create → install deps" in prompt
    assert "cpu-basic sandbox is already available" not in prompt
    assert "started automatically for normal CPU work" not in tool_specs.get(
        "bash", ""
    )
    assert "started automatically" not in tool_specs.get("sandbox_create", "")


def test_local_tool_runtime_excludes_sandbox_create():
    tool_names = {tool.name for tool in create_builtin_tools(local_mode=True)}

    assert {"bash", "read", "write", "edit"} <= tool_names
    assert "sandbox_create" not in tool_names


def test_sandbox_tool_runtime_includes_sandbox_create(monkeypatch):
    monkeypatch.setenv("AGENT_REMOTE_SANDBOX", "1")
    tool_names = {tool.name for tool in create_builtin_tools(local_mode=False)}

    assert {"sandbox_create", "bash", "read", "write", "edit"} <= tool_names
