"""Cache-breakpoint placement for Anthropic requests.

See agent/core/prompt_caching.py. Anthropic caches the prefix ending at each
``cache_control`` marker, so these tests are really about *where* the markers
land and about not mutating the caller's message list.
"""

from litellm import Message

from agent.core.prompt_caching import with_prompt_caching

ANTHROPIC = "anthropic/claude-opus-4-7"


def _blocks(message):
    content = message["content"] if isinstance(message, dict) else message.content
    return content


def _has_marker(message) -> bool:
    content = _blocks(message)
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
        for b in content
    )


def _marked_indices(messages) -> list[int]:
    return [i for i, m in enumerate(messages) if _has_marker(m)]


# ── passthrough ────────────────────────────────────────────────────────────


def test_non_anthropic_models_are_untouched():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    tools = [{"name": "t"}]
    out_messages, out_tools = with_prompt_caching(messages, tools, "openai/gpt-5.5")
    assert out_messages is messages
    assert out_tools is tools


def test_custom_inference_model_is_untouched():
    """The fork routes some ids to CUSTOM_INFERENCE_*; those must pass through."""
    messages = [{"role": "system", "content": "sys"}]
    out, _ = with_prompt_caching(messages, None, "minimax/minimax-m2.7")
    assert out is messages


def test_missing_model_name_is_untouched():
    messages = [{"role": "system", "content": "sys"}]
    out, tools = with_prompt_caching(messages, None, None)
    assert out is messages
    assert tools is None


def test_empty_messages_still_marks_tools():
    out, tools = with_prompt_caching([], [{"name": "a"}, {"name": "b"}], ANTHROPIC)
    assert out == []
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in tools[0]


# ── breakpoint placement ───────────────────────────────────────────────────


def test_system_message_is_marked():
    messages = [{"role": "system", "content": "sys"}]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == [0]
    assert _blocks(out[0]) == [
        {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}
    ]


def test_single_turn_marks_only_system_not_the_live_input():
    """With [system, user] the user message *is* the current input — never cache it."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "the question"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == [0]


def test_sliding_breakpoint_lands_on_previous_user_turn():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "second"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    # index 1 is the newest cacheable message that is not the live input (3).
    assert _marked_indices(out) == [0, 1]


def test_sliding_breakpoint_skips_assistant_and_tool_roles():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "calling a tool"},
        {"role": "tool", "content": "tool output"},
        {"role": "assistant", "content": "still working"},
        {"role": "user", "content": "live input"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == [0, 1]


def test_sliding_breakpoint_advances_as_conversation_grows():
    """The whole point: coverage grows instead of stopping at the system prompt."""
    base = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    grown = base + [
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "live"},
    ]
    _, _ = with_prompt_caching(base, None, ANTHROPIC)
    out_grown, _ = with_prompt_caching(grown, None, ANTHROPIC)
    assert _marked_indices(out_grown) == [0, 3]


def test_never_more_than_three_breakpoints():
    """Anthropic allows 4; tools + system + sliding must stay within that."""
    messages = [{"role": "system", "content": "sys"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(20)
    ]
    out, tools = with_prompt_caching(messages, [{"name": "t"}], ANTHROPIC)
    marked_tools = sum(1 for t in tools if "cache_control" in t)
    assert len(_marked_indices(out)) + marked_tools <= 4


def test_no_duplicate_breakpoint_when_system_is_the_only_candidate():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "a"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == [0]


def test_missing_system_message_still_gets_a_sliding_breakpoint():
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "live"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == [0]


def test_empty_content_is_not_a_cache_target():
    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": ""},
        {"role": "user", "content": "live"},
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert _marked_indices(out) == []


# ── no mutation of caller state ────────────────────────────────────────────


def test_caller_messages_are_not_mutated():
    """ContextManager.items is passed in directly; markers must not persist."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "live"},
    ]
    before = [dict(m) for m in messages]
    with_prompt_caching(messages, None, ANTHROPIC)
    assert messages == before


def test_litellm_message_objects_are_not_mutated():
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="u1"),
        Message(role="assistant", content="a1"),
        Message(role="user", content="live"),
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    assert messages[0].content == "sys"
    assert messages[1].content == "u1"
    assert _marked_indices(out) == [0, 1]


def test_caller_tools_are_not_mutated():
    tools = [{"name": "a"}, {"name": "b"}]
    with_prompt_caching([], tools, ANTHROPIC)
    assert tools == [{"name": "a"}, {"name": "b"}]


def test_already_blocked_content_gets_marker_on_last_text_block():
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "part one"},
                {"type": "text", "text": "part two"},
            ],
        },
    ]
    out, _ = with_prompt_caching(messages, None, ANTHROPIC)
    blocks = _blocks(out[0])
    assert "cache_control" not in blocks[0]
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}


# ── refresh_system_prompt must not invalidate the prefix for free ───────────


def _session_with(items, rendered):
    """Minimal stand-in exercising Session.refresh_system_prompt unbound."""
    from types import SimpleNamespace

    return SimpleNamespace(
        context_manager=SimpleNamespace(items=items),
        _fresh_system_message=lambda: rendered,
    )


def test_refresh_system_prompt_is_a_noop_when_content_is_unchanged():
    """A no-change re-render would still cost a full-price turn on Anthropic."""
    from agent.core.session import Session

    items = [Message(role="system", content="same text")]
    original = items[0]
    session = _session_with(items, Message(role="system", content="same text"))

    assert Session.refresh_system_prompt(session) is False
    assert items[0] is original


def test_refresh_system_prompt_swaps_when_content_changed():
    from agent.core.session import Session

    items = [Message(role="system", content="old text")]
    session = _session_with(items, Message(role="system", content="new text"))

    assert Session.refresh_system_prompt(session) is True
    assert items[0].content == "new text"


def test_refresh_system_prompt_inserts_when_no_system_message_present():
    from agent.core.session import Session

    items = [Message(role="user", content="hi")]
    session = _session_with(items, Message(role="system", content="sys"))

    assert Session.refresh_system_prompt(session) is True
    assert items[0].role == "system"
    assert len(items) == 2


def test_refresh_system_prompt_handles_unavailable_render():
    from agent.core.session import Session

    items = [Message(role="system", content="keep me")]
    session = _session_with(items, None)

    assert Session.refresh_system_prompt(session) is False
    assert items[0].content == "keep me"
