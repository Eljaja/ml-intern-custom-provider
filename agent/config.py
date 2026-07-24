import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastmcp.mcp_config import (
    RemoteMCPServer,
    StdioMCPServer,
)
from pydantic import BaseModel

from agent.messaging.models import MessagingConfig
from agent.project_root import find_project_root

# These two are the canonical server config types for MCP servers.
MCPServerConfig = StdioMCPServer | RemoteMCPServer

_PROJECT_ROOT = find_project_root()


class Config(BaseModel):
    """Configuration manager"""

    model_name: str
    mcpServers: dict[str, MCPServerConfig] = {}
    save_sessions: bool = True
    session_dataset_repo: str = "smolagents/ml-intern-sessions"
    # Per-user private dataset that mirrors each session in Claude Code JSONL
    # format so the HF Agent Trace Viewer auto-renders it
    # (https://huggingface.co/changelog/agent-trace-viewer). Created private
    # on first use; user flips it public via /share-traces. ``{hf_user}`` is
    # substituted at upload time from the authenticated HF username.
    share_traces: bool = True
    personal_trace_repo_template: str = "{hf_user}/ml-intern-sessions"
    auto_save_interval: int = 1  # Save every N user turns (0 = disabled)
    # Mid-turn heartbeat: save + upload every N seconds while events are being
    # emitted. Guards against losing trace data on long-running turns that
    # crash before turn_complete (e.g. a long sandbox or network call).
    # 0 = disabled. Consumed by agent.core.telemetry.HeartbeatSaver.
    heartbeat_interval_s: int = 60
    yolo_mode: bool = False  # Auto-approve all tool calls without confirmation
    max_iterations: int = 300  # Max LLM calls per agent turn (-1 = unlimited)

    # Permission control parameters
    auto_file_upload: bool = False
    tool_runtime: Literal["local", "sandbox"] = "local"

    # Reasoning effort *preference* — the ceiling the user wants. The probe
    # on `/model` walks a cascade down from here (``max`` → ``xhigh`` → ``high``
    # → …) and caches per-model what the provider actually accepted in
    # ``Session.model_effective_effort``. Default ``max`` because we'd rather
    # burn tokens thinking than ship a wrong ML recipe; the cascade lands on
    # whichever level the model supports (``high`` for GPT-5 / HF router,
    # ``xhigh`` or ``max`` for Anthropic 4.6 / 4.7). ``None`` = thinking off.
    # Valid values: None | "minimal" | "low" | "medium" | "high" | "xhigh" | "max"
    reasoning_effort: str | None = "max"

    # Post-turn skill reflection: an extra LLM call after every substantive turn
    # that decides whether to save a reusable procedure to the user's skill store
    # (agent.core.agent_loop._maybe_reflect_skill). It runs detached from the turn
    # at a pinned-low effort, but it is still a second model call per turn. Set
    # false to switch it off; the agent can still call skill_manage explicitly.
    skill_reflection: bool = True

    messaging: MessagingConfig = MessagingConfig()


USER_CONFIG_ENV_VAR = "ML_INTERN_CLI_CONFIG"
DEFAULT_USER_CONFIG_PATH = (
    Path.home() / ".config" / "ml-intern" / "cli_agent_config.json"
)
SLACK_DEFAULT_DESTINATION = "slack.default"
SLACK_DEFAULT_AUTO_EVENT_TYPES = ["approval_required", "error", "turn_complete"]
ZULIP_DEFAULT_DESTINATION = "zulip.default"
ZULIP_DEFAULT_TOPIC = "ml-intern"
ZULIP_DEFAULT_AUTO_EVENT_TYPES = ["approval_required", "error", "turn_complete"]


def _deep_merge_config(
    base: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_config(current, value)
        else:
            merged[key] = value
    return merged


def _load_json_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a JSON object")
    return data


def _load_user_config() -> dict[str, Any]:
    raw_path = os.environ.get(USER_CONFIG_ENV_VAR)
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"{USER_CONFIG_ENV_VAR} points to missing config file: {path}"
            )
        return _load_json_config(path)

    if DEFAULT_USER_CONFIG_PATH.exists():
        return _load_json_config(DEFAULT_USER_CONFIG_PATH)
    return {}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_list(name: str) -> list[str] | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class _EnvProvider:
    """How one notification provider is configured from the environment."""

    name: str
    enable_env: str
    destination_env: str
    default_destination: str
    auto_events_env: str
    default_auto_events: list[str]
    build: Callable[[], dict[str, Any] | None]


def _slack_destination_from_env() -> dict[str, Any] | None:
    token = (os.environ.get("SLACK_BOT_TOKEN") or "").strip()
    channel = (
        os.environ.get("SLACK_CHANNEL_ID") or os.environ.get("SLACK_CHANNEL") or ""
    ).strip()
    if not token or not channel:
        return None
    return {
        "provider": "slack",
        "token": token,
        "channel": channel,
        "allow_agent_tool": _env_bool("ML_INTERN_SLACK_ALLOW_AGENT_TOOL", True),
        "allow_auto_events": _env_bool("ML_INTERN_SLACK_ALLOW_AUTO_EVENTS", True),
    }


def _zulip_destination_from_env() -> dict[str, Any] | None:
    site = (os.environ.get("ZULIP_SITE") or "").strip().rstrip("/")
    email = (
        os.environ.get("ZULIP_BOT_EMAIL") or os.environ.get("ZULIP_EMAIL") or ""
    ).strip()
    api_key = (os.environ.get("ZULIP_API_KEY") or "").strip()
    if not site or not email or not api_key:
        return None

    message_type = (os.environ.get("ZULIP_MESSAGE_TYPE") or "stream").strip().lower()
    if message_type not in {"stream", "private"}:
        message_type = "stream"

    stream = (os.environ.get("ZULIP_STREAM") or "").strip() or None
    to = (os.environ.get("ZULIP_TO") or "").strip() or None
    if message_type == "stream" and not stream:
        return None
    if message_type == "private" and not to:
        return None

    destination: dict[str, Any] = {
        "provider": "zulip",
        "site": site,
        "email": email,
        "api_key": api_key,
        "message_type": message_type,
        "topic": (os.environ.get("ZULIP_TOPIC") or ZULIP_DEFAULT_TOPIC).strip(),
        "allow_agent_tool": _env_bool("ML_INTERN_ZULIP_ALLOW_AGENT_TOOL", True),
        "allow_auto_events": _env_bool("ML_INTERN_ZULIP_ALLOW_AUTO_EVENTS", True),
    }
    if message_type == "stream":
        destination["stream"] = stream
    else:
        destination["to"] = to
    return destination


# One entry per notification provider configurable from the environment. Adding a
# provider here is all it takes; the two implementations used to be near-identical
# 40-line copies that had already drifted apart in which code path applied them.
_ENV_PROVIDERS: tuple[_EnvProvider, ...] = (
    _EnvProvider(
        name="slack",
        enable_env="ML_INTERN_SLACK_NOTIFICATIONS",
        destination_env="ML_INTERN_SLACK_DESTINATION",
        default_destination=SLACK_DEFAULT_DESTINATION,
        auto_events_env="ML_INTERN_SLACK_AUTO_EVENTS",
        default_auto_events=SLACK_DEFAULT_AUTO_EVENT_TYPES,
        build=_slack_destination_from_env,
    ),
    _EnvProvider(
        name="zulip",
        enable_env="ML_INTERN_ZULIP_NOTIFICATIONS",
        destination_env="ML_INTERN_ZULIP_DESTINATION",
        default_destination=ZULIP_DEFAULT_DESTINATION,
        auto_events_env="ML_INTERN_ZULIP_AUTO_EVENTS",
        default_auto_events=ZULIP_DEFAULT_AUTO_EVENT_TYPES,
        build=_zulip_destination_from_env,
    ),
)


def _apply_env_provider(
    raw_config: dict[str, Any], provider: _EnvProvider
) -> dict[str, Any]:
    """Merge one provider's env-configured destination into ``raw_config``."""
    if not _env_bool(provider.enable_env, True):
        return raw_config

    destination = provider.build()
    if destination is None:
        return raw_config

    config = dict(raw_config)
    messaging = dict(config.get("messaging") or {})
    destinations = dict(messaging.get("destinations") or {})

    name = (
        os.environ.get(provider.destination_env) or provider.default_destination
    ).strip()
    # An explicit entry in the JSON config wins over env autoconfiguration.
    if name not in destinations:
        destinations[name] = destination

    auto_events = _env_list(provider.auto_events_env)
    if auto_events is not None:
        messaging["auto_event_types"] = auto_events
    elif "auto_event_types" not in messaging:
        messaging["auto_event_types"] = provider.default_auto_events

    messaging["enabled"] = True
    messaging["destinations"] = destinations
    config["messaging"] = messaging
    return config


def apply_messaging_env_defaults(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Apply every env-configured notification destination (.env).

    Called unconditionally from ``load_config``, i.e. for the web backend too.
    Slack used to be applied only under ``include_user_defaults`` while Zulip was
    applied always, so ``SLACK_BOT_TOKEN`` in .env silently did nothing in web
    sessions (backend/session_manager.py loads the config without that flag).
    """
    for provider in _ENV_PROVIDERS:
        raw_config = _apply_env_provider(raw_config, provider)
    return raw_config


def apply_slack_user_defaults(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Backwards-compatible alias kept for existing imports and tests."""
    return _apply_env_provider(raw_config, _ENV_PROVIDERS[0])


def apply_zulip_user_defaults(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Backwards-compatible alias kept for existing imports and tests."""
    return _apply_env_provider(raw_config, _ENV_PROVIDERS[1])


def substitute_env_vars(obj: Any) -> Any:
    """
    Recursively substitute environment variables in any data structure.

    Supports ${VAR_NAME} syntax for required variables and ${VAR_NAME:-default} for optional.
    """
    if isinstance(obj, str):
        pattern = r"\$\{([^}:]+)(?::(-)?([^}]*))?\}"

        def replacer(match):
            var_name = match.group(1)
            has_default = match.group(2) is not None
            default_value = match.group(3) if has_default else None

            env_value = os.environ.get(var_name)

            if env_value is not None:
                return env_value
            elif has_default:
                return default_value or ""
            else:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set. "
                    f"Add it to your .env file."
                )

        return re.sub(pattern, replacer, obj)

    elif isinstance(obj, dict):
        return {key: substitute_env_vars(value) for key, value in obj.items()}

    elif isinstance(obj, list):
        return [substitute_env_vars(item) for item in obj]

    return obj


def load_config(
    config_path: str = "config.json",
    include_user_defaults: bool = False,
) -> Config:
    """
    Load configuration with environment variable substitution.

    Use ${VAR_NAME} in your JSON for any secret.
    Automatically loads from .env file.
    """
    # Load .env from project root first (so it works from any directory),
    # then CWD .env can override if present
    load_dotenv(_PROJECT_ROOT / ".env")
    load_dotenv(override=False)

    raw_config = _load_json_config(Path(config_path))
    if include_user_defaults:
        raw_config = _deep_merge_config(raw_config, _load_user_config())
    raw_config = apply_messaging_env_defaults(raw_config)

    config_with_env = substitute_env_vars(raw_config)
    return Config.model_validate(config_with_env)
