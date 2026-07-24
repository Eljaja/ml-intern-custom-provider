"""Failure ledger and the end-of-turn completion guard.

Two gaps this closes:

* Compaction folds the conversation middle into a summary; "what I already tried
  and ruled out" is what a readable summary drops first, so a compacted agent
  retries commands that already failed.
* Turn termination was "the model stopped calling tools". Nothing noticed a turn
  ending on a confident summary while half its tool calls had failed.
"""

from types import SimpleNamespace

import pytest

from agent.core import attempt_log
from agent.core.agent_loop import (
    _completion_guard_prompt,
    _should_warn_wrap_up,
    _wrap_up_prompt,
)


def _session(**kwargs):
    return SimpleNamespace(current_plan=[], **kwargs)


# ── ledger ─────────────────────────────────────────────────────────────────


def test_failures_are_recorded_and_rendered():
    session = _session()
    attempt_log.record_failure(
        session, "bash", {"command": "pip install flash-attn"}, "error: no wheel"
    )

    records = attempt_log.unresolved_failures(session)
    assert len(records) == 1
    assert records[0].tool == "bash"
    assert "flash-attn" in records[0].args
    assert "no wheel" in records[0].error

    block = attempt_log.format_block(session)
    assert "bash" in block
    assert "Do not repeat these as-is" in block


def test_a_later_success_resolves_earlier_failures_of_the_same_tool():
    """Fixing the arguments is the normal repair path, so matching is by tool."""
    session = _session()
    attempt_log.record_failure(session, "bash", {"command": "a"}, "boom")
    attempt_log.record_failure(session, "bash", {"command": "b"}, "boom again")
    assert len(attempt_log.unresolved_failures(session)) == 2

    attempt_log.record_success(session, "bash")
    assert attempt_log.unresolved_failures(session) == []
    assert attempt_log.format_block(session) == ""


def test_success_of_a_different_tool_does_not_resolve_anything():
    session = _session()
    attempt_log.record_failure(session, "bash", None, "boom")
    attempt_log.record_success(session, "hf_repo_files")
    assert len(attempt_log.unresolved_failures(session)) == 1


def test_clean_session_renders_an_empty_block():
    assert attempt_log.format_block(_session()) == ""
    assert attempt_log.unresolved_failures(_session()) == []


def test_ledger_is_capped_and_prefers_keeping_unresolved_records():
    session = _session()
    for i in range(attempt_log.MAX_RECORDS + 10):
        attempt_log.record_failure(session, f"tool-{i}", None, "boom")
    log = session.attempt_log
    assert len(log.records) <= attempt_log.MAX_RECORDS
    # Nothing succeeded, so everything retained must still be unresolved.
    assert len(log.unresolved()) == len(log.records)


def test_long_output_and_args_are_truncated():
    session = _session()
    attempt_log.record_failure(session, "bash", {"c": "x" * 5000}, "y" * 5000)
    record = attempt_log.unresolved_failures(session)[0]
    assert len(record.args) < 400
    assert len(record.error) < 600


def test_clear_empties_the_ledger():
    session = _session()
    attempt_log.record_failure(session, "bash", None, "boom")
    attempt_log.clear(session)
    assert attempt_log.unresolved_failures(session) == []


def test_ledger_tolerates_a_session_it_cannot_attach_to():
    """Slots-based or frozen stand-ins must not blow up the tool loop."""

    class NoAttrs:
        __slots__ = ()

    attempt_log.record_failure(NoAttrs(), "bash", None, "boom")
    assert attempt_log.unresolved_failures(NoAttrs()) == []
    assert attempt_log.record_success(NoAttrs(), "bash") is None


# ── completion guard ───────────────────────────────────────────────────────


def test_guard_is_silent_on_a_clean_finish():
    assert _completion_guard_prompt(_session()) is None


def test_guard_reports_unfinished_plan_items_first():
    session = _session()
    session.current_plan = [
        {"id": "1", "content": "train the model", "status": "pending"}
    ]
    attempt_log.record_failure(session, "bash", None, "boom")

    prompt = _completion_guard_prompt(session)
    assert "CONTINUATION GUARD" in prompt
    assert "train the model" in prompt


def test_guard_catches_a_turn_ending_on_unresolved_failures():
    session = _session()
    attempt_log.record_failure(
        session, "hf_repo_files", {"operation": "upload"}, "403 forbidden"
    )

    prompt = _completion_guard_prompt(session)
    assert "COMPLETION GUARD" in prompt
    assert "hf_repo_files" in prompt
    assert "403 forbidden" in prompt


def test_guard_clears_once_the_failure_is_resolved():
    session = _session()
    attempt_log.record_failure(session, "bash", None, "boom")
    assert _completion_guard_prompt(session) is not None

    attempt_log.record_success(session, "bash")
    assert _completion_guard_prompt(session) is None


# ── iteration budget ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("iteration", "budget", "expected"),
    [
        (0, 300, False),
        (200, 300, False),
        (255, 300, True),  # 85%
        (299, 300, True),
        (0, -1, False),  # unlimited never warns
        (18, 19, False),  # budget too small for the warning to be actionable
        (100, 100, True),
    ],
)
def test_wrap_up_threshold(iteration, budget, expected):
    assert _should_warn_wrap_up(iteration, budget) is expected


def test_wrap_up_prompt_states_the_remaining_budget():
    prompt = _wrap_up_prompt(255, 300)
    assert "255 of 300" in prompt
    assert "45 remain" in prompt
    assert "Do not start a new line of investigation" in prompt


# ── survives compaction ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compaction_appends_the_failure_ledger_to_the_summary(monkeypatch):
    """The ledger is the part a readable summary drops first, so append it verbatim."""
    from litellm import Message

    from agent.context_manager import manager as manager_module

    async def fake_summarize(*_args, **_kwargs):
        return ("Narrative summary that forgot the failures.", 10)

    monkeypatch.setattr(manager_module, "summarize_messages", fake_summarize)
    # Compaction verifies it got under the threshold afterwards; the real
    # recount needs a live tokenizer, so report a small number.
    monkeypatch.setattr(
        manager_module.ContextManager,
        "_recompute_usage",
        lambda self, _m: setattr(self, "running_context_usage", 10),
    )
    monkeypatch.setattr("litellm.token_counter", lambda **_k: 10)

    # untouched_messages=2 so the walk-back lands on the late user message and
    # leaves a middle to summarise.
    cm = manager_module.ContextManager(
        tool_specs=[], model_max_tokens=1000, untouched_messages=2
    )
    cm.items = [
        Message(role="system", content="sys"),
        Message(role="user", content="task"),
        *[Message(role="assistant", content=f"step {i}") for i in range(10)],
        Message(role="user", content="recent"),
        Message(role="assistant", content="final"),
    ]
    cm.running_context_usage = 10_000  # force needs_compaction

    session = _session()
    attempt_log.record_failure(
        session, "bash", {"command": "pip install flash-attn"}, "no matching wheel"
    )

    await cm.compact(model_name="anthropic/claude-opus-4-7", session=session)

    summary_text = "\n".join(
        str(m.content) for m in cm.items if getattr(m, "role", "") == "assistant"
    )
    assert "Narrative summary" in summary_text
    assert "flash-attn" in summary_text, "the ledger must survive compaction"
    assert "no matching wheel" in summary_text


def test_compaction_prompt_addresses_the_agent_not_a_newcomer():
    """It used to ask for a briefing 'for someone who has never worked on this'."""
    from agent.context_manager.manager import _COMPACT_PROMPT

    assert "future self" in _COMPACT_PROMPT
    assert "TRIED AND RULED OUT" in _COMPACT_PROMPT
    assert "never worked on this project" not in _COMPACT_PROMPT
