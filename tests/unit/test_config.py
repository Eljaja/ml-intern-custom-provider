import json

import pytest
from pydantic import ValidationError

from agent import config as config_module


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_slack_env_defaults_apply_without_include_user_defaults(tmp_path, monkeypatch):
    """Env-configured destinations no longer depend on include_user_defaults.

    They used to: Slack was applied only under that flag while Zulip was applied
    always, so SLACK_BOT_TOKEN in .env silently did nothing for web sessions
    (backend/session_manager.py loads the config without it). Both providers now
    behave the same.
    """
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {
                "enabled": False,
                "destinations": {},
            },
        },
    )
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path))

    assert config.messaging.enabled
    assert "slack.default" in config.messaging.destinations


def test_no_messaging_env_leaves_config_untouched(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {"enabled": False, "destinations": {}},
        },
    )
    for var in (
        "SLACK_BOT_TOKEN",
        "SLACK_CHANNEL_ID",
        "SLACK_CHANNEL",
        "ZULIP_SITE",
        "ZULIP_BOT_EMAIL",
        "ZULIP_EMAIL",
        "ZULIP_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    config = config_module.load_config(str(config_path))

    assert not config.messaging.enabled
    assert config.messaging.destinations == {}


def test_slack_and_zulip_env_defaults_coexist(tmp_path, monkeypatch):
    """Both providers configured at once should both land as destinations."""
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    monkeypatch.setenv("ZULIP_SITE", "https://chat.example.com")
    monkeypatch.setenv("ZULIP_BOT_EMAIL", "bot@example.com")
    monkeypatch.setenv("ZULIP_API_KEY", "zkey")
    monkeypatch.setenv("ZULIP_STREAM", "ml-agent")

    config = config_module.load_config(str(config_path))

    assert set(config.messaging.destinations) == {"slack.default", "zulip.default"}
    assert config.messaging.destinations["slack.default"].provider == "slack"
    assert config.messaging.destinations["zulip.default"].provider == "zulip"


def test_explicit_json_destination_wins_over_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {
                "enabled": True,
                "destinations": {
                    "slack.default": {
                        "provider": "slack",
                        "token": "from-json",
                        "channel": "C-json",
                    }
                },
            },
        },
    )
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-from-env")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C-env")

    config = config_module.load_config(str(config_path))

    assert config.messaging.destinations["slack.default"].token == "from-json"


def test_load_config_applies_slack_user_defaults_from_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    monkeypatch.delenv("ML_INTERN_CLI_CONFIG", raising=False)
    monkeypatch.setattr(
        config_module,
        "DEFAULT_USER_CONFIG_PATH",
        tmp_path / "missing-user-config.json",
    )
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.messaging.enabled
    assert config.messaging.auto_event_types == [
        "approval_required",
        "error",
        "turn_complete",
    ]
    destination = config.messaging.destinations["slack.default"]
    assert destination.token == "xoxb-test"
    assert destination.channel == "C123"
    assert destination.allow_agent_tool
    assert destination.allow_auto_events


def test_load_config_applies_zulip_defaults_from_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL_ID", raising=False)
    monkeypatch.setenv("ZULIP_SITE", "https://chat.example.com")
    monkeypatch.setenv("ZULIP_BOT_EMAIL", "bot@example.com")
    monkeypatch.setenv("ZULIP_API_KEY", "zulip-key")
    monkeypatch.setenv("ZULIP_STREAM", "ml-agent")
    monkeypatch.setenv("ZULIP_TOPIC", "alerts")

    config = config_module.load_config(str(config_path))

    assert config.messaging.enabled
    destination = config.messaging.destinations["zulip.default"]
    assert destination.provider == "zulip"
    assert destination.site == "https://chat.example.com"
    assert destination.email == "bot@example.com"
    assert destination.api_key == "zulip-key"
    assert destination.stream == "ml-agent"
    assert destination.topic == "alerts"


def test_zulip_user_defaults_can_be_disabled(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    monkeypatch.setenv("ML_INTERN_ZULIP_NOTIFICATIONS", "false")
    monkeypatch.setenv("ZULIP_SITE", "https://chat.example.com")
    monkeypatch.setenv("ZULIP_BOT_EMAIL", "bot@example.com")
    monkeypatch.setenv("ZULIP_API_KEY", "zulip-key")
    monkeypatch.setenv("ZULIP_STREAM", "ml-agent")

    config = config_module.load_config(str(config_path))

    assert not config.messaging.enabled
    assert config.messaging.destinations == {}


def test_load_config_merges_user_config_before_env_substitution(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    user_config_path = tmp_path / "user-config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    _write_json(
        user_config_path,
        {
            "messaging": {
                "enabled": True,
                "auto_event_types": ["approval_required"],
                "destinations": {
                    "slack.team": {
                        "provider": "slack",
                        "token": "${USER_SLACK_TOKEN}",
                        "channel": "C999",
                        "allow_agent_tool": False,
                        "allow_auto_events": True,
                    },
                },
            },
        },
    )
    monkeypatch.setenv("ML_INTERN_CLI_CONFIG", str(user_config_path))
    monkeypatch.setenv("ML_INTERN_SLACK_NOTIFICATIONS", "0")
    monkeypatch.setenv("USER_SLACK_TOKEN", "xoxb-user")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.messaging.enabled
    assert config.messaging.auto_event_types == ["approval_required"]
    assert set(config.messaging.destinations) == {"slack.team"}
    destination = config.messaging.destinations["slack.team"]
    assert destination.token == "xoxb-user"
    assert destination.channel == "C999"
    assert not destination.allow_agent_tool
    assert destination.allow_auto_events


def test_slack_user_defaults_can_be_disabled(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "model_name": "moonshotai/Kimi-K2.6",
            "messaging": {
                "enabled": False,
                "destinations": {},
            },
        },
    )
    monkeypatch.delenv("ML_INTERN_CLI_CONFIG", raising=False)
    monkeypatch.setattr(
        config_module,
        "DEFAULT_USER_CONFIG_PATH",
        tmp_path / "missing-user-config.json",
    )
    monkeypatch.setenv("ML_INTERN_SLACK_NOTIFICATIONS", "false")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert not config.messaging.enabled
    assert config.messaging.destinations == {}


def test_tool_runtime_defaults_to_local(tmp_path):
    config_path = tmp_path / "config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})

    config = config_module.load_config(str(config_path))

    assert config.tool_runtime == "local"


def test_user_config_can_set_sandbox_tool_runtime(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    user_config_path = tmp_path / "user-config.json"
    _write_json(config_path, {"model_name": "moonshotai/Kimi-K2.6"})
    _write_json(user_config_path, {"tool_runtime": "sandbox"})
    monkeypatch.setenv("ML_INTERN_CLI_CONFIG", str(user_config_path))

    config = config_module.load_config(str(config_path), include_user_defaults=True)

    assert config.tool_runtime == "sandbox"


def test_invalid_tool_runtime_is_rejected(tmp_path):
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {"model_name": "moonshotai/Kimi-K2.6", "tool_runtime": "hybrid"},
    )

    with pytest.raises(ValidationError):
        config_module.load_config(str(config_path))


def test_autonomous_prompt_section_is_gated(tmp_path, monkeypatch):
    """The never-stop-working block is wrong for interactive chat."""
    from agent.context_manager.manager import ContextManager

    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))

    headless = ContextManager(tool_specs=[], autonomous_mode=True).system_prompt
    assert "Autonomous / headless mode" in headless
    assert "NEVER STOP WORKING" in headless
    assert "Interactive mode" not in headless

    interactive = ContextManager(tool_specs=[], autonomous_mode=False).system_prompt
    assert "NEVER STOP WORKING" not in interactive
    assert "Interactive mode" in interactive
    # Regression guard: a missing template variable renders as falsey, which is
    # how this section would silently disappear from headless runs.
    assert "{% if" not in interactive


def test_tool_calling_contract_is_always_present(tmp_path, monkeypatch):
    from agent.context_manager.manager import ContextManager

    monkeypatch.setenv("ML_INTERN_SKILLS_DIR", str(tmp_path))
    for autonomous in (True, False):
        prompt = ContextManager(tool_specs=[], autonomous_mode=autonomous).system_prompt
        assert "Tool calling contract" in prompt
        assert "source of truth" in prompt


def test_headless_main_requests_autonomous_mode():
    """agent.main.headless_main must pass the flag; nothing else sets it."""
    import inspect

    from agent import main as main_module

    source = inspect.getsource(main_module.headless_main)
    assert "autonomous_mode=True" in source
