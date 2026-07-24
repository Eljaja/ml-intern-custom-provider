"""Startup guard for shell-access-without-auth.

See backend/runtime_guard.py — AGENT_LOCAL_MODE=1 plus a missing
OAUTH_CLIENT_ID means unauthenticated arbitrary command execution for anyone
who can reach the port.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from runtime_guard import (  # noqa: E402
    UnsafeRuntimeConfigError,
    assert_safe_runtime,
    unsafe_runtime_reason,
)


def test_local_mode_without_auth_is_refused():
    reason = unsafe_runtime_reason({"AGENT_LOCAL_MODE": "1"})
    assert reason is not None
    assert "OAUTH_CLIENT_ID" in reason
    with pytest.raises(UnsafeRuntimeConfigError):
        assert_safe_runtime({"AGENT_LOCAL_MODE": "1"})


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_all_truthy_spellings_of_local_mode_are_caught(value):
    assert unsafe_runtime_reason({"AGENT_LOCAL_MODE": value}) is not None


def test_local_mode_with_oauth_configured_is_allowed():
    env = {"AGENT_LOCAL_MODE": "1", "OAUTH_CLIENT_ID": "abc123"}
    assert unsafe_runtime_reason(env) is None
    assert_safe_runtime(env)


def test_explicit_acknowledgement_is_allowed():
    env = {
        "AGENT_LOCAL_MODE": "1",
        "ML_INTERN_ALLOW_UNAUTHENTICATED_LOCAL_MODE": "1",
    }
    assert unsafe_runtime_reason(env) is None
    assert_safe_runtime(env)


def test_remote_sandbox_mode_needs_no_acknowledgement():
    """Without AGENT_LOCAL_MODE there is no shell on this host to protect."""
    assert unsafe_runtime_reason({}) is None
    assert unsafe_runtime_reason({"AGENT_LOCAL_MODE": "0"}) is None


def test_blank_oauth_client_id_does_not_count_as_configured():
    """AUTH_ENABLED is bool(os.environ[...]), so whitespace must not pass."""
    env = {"AGENT_LOCAL_MODE": "1", "OAUTH_CLIENT_ID": "   "}
    assert unsafe_runtime_reason(env) is not None
