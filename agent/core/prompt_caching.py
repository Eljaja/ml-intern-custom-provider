"""Anthropic prompt caching breakpoints for outgoing LLM requests.

Caching is GA on Anthropic's API and natively supported by litellm >=1.83 via
``cache_control`` blocks. Anthropic allows up to 4 breakpoints per request and
caches the whole *prefix* ending at each one, so where they sit decides how much
of the turn is re-billed at full input price.

We place up to three:

  1. The tool block — caches all tool definitions.
  2. The system message — the rendered system prompt.
  3. A *sliding* breakpoint on the newest cacheable system/user message that is
     not the current turn's input. This is the one that matters as a session
     grows: with only (1) and (2), everything after the system prompt was
     re-sent at full price every turn, which on a long agentic session is the
     bulk of the context. The newest message is deliberately left uncached — it
     differs every turn, so a breakpoint there could never be read back.

Keeping (2) alongside (3) is deliberate. When something invalidates the longer
prefix — a system-prompt re-render mid-session, edited history, a compaction —
the request still reads cache at the system/tools boundary instead of paying
full price for the whole context.

Non-Anthropic models (HF router, OpenAI, custom OpenAI-compatible endpoints) are
passed through unchanged; they either cache prefixes automatically or ignore the
markers.
"""

from typing import Any

_CACHE_CONTROL = {"type": "ephemeral"}
_CACHEABLE_ROLES = {"system", "user"}


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict):
        return message.get("role")
    return getattr(message, "role", None)


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _message_to_dict(message: Any) -> dict[str, Any]:
    """Copy a message into a plain dict we may safely rewrite.

    litellm ``Message`` objects are shared with ``ContextManager.items``; they
    must never be mutated, or cache markers leak into persisted history.
    """
    if isinstance(message, dict):
        return dict(message)
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        try:
            return dump(exclude_none=True)
        except TypeError:
            return dump()
    return {"role": _message_role(message), "content": _message_content(message)}


def _has_cacheable_text(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content)
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and bool(block.get("text"))
        for block in content
    )


def _content_with_cache_control(content: Any) -> Any:
    """Return content with ``cache_control`` on its last non-empty text block."""
    if isinstance(content, str):
        return [
            {"type": "text", "text": content, "cache_control": dict(_CACHE_CONTROL)}
        ]

    if not isinstance(content, list):
        return content

    blocks = [dict(block) if isinstance(block, dict) else block for block in content]
    for idx in range(len(blocks) - 1, -1, -1):
        block = blocks[idx]
        if (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and bool(block.get("text"))
        ):
            cached = dict(block)
            cached["cache_control"] = dict(_CACHE_CONTROL)
            blocks[idx] = cached
            break
    return blocks


def _sliding_target_index(messages: list[Any], *, skip: int | None) -> int | None:
    """Index of the newest cacheable message that is not the current turn's input.

    Walks back from the second-to-last entry. ``skip`` is the index that already
    carries a breakpoint (the system message), so two of the four available
    markers are never spent on the same position.
    """
    if len(messages) < 2:
        return None

    for idx in range(len(messages) - 2, -1, -1):
        if idx == skip:
            return None
        if _message_role(messages[idx]) not in _CACHEABLE_ROLES:
            continue
        if _has_cacheable_text(_message_content(messages[idx])):
            return idx
    return None


def _tools_with_cache_control(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return tools
    cached = list(tools)
    last = dict(cached[-1])
    last["cache_control"] = dict(_CACHE_CONTROL)
    cached[-1] = last
    return cached


def with_prompt_caching(
    messages: list[Any],
    tools: list[dict] | None,
    model_name: str | None,
) -> tuple[list[Any], list[dict] | None]:
    """Return (messages, tools) with cache_control breakpoints for Anthropic.

    No-op for non-Anthropic models. Original objects are not mutated; a fresh
    list with replaced entries is returned, so callers that share the underlying
    ``ContextManager.items`` list don't see their persisted history rewritten.
    """
    if not model_name or "anthropic" not in model_name:
        return messages, tools

    tools = _tools_with_cache_control(tools)

    if not messages:
        return messages, tools

    out = list(messages)

    system_idx: int | None = None
    if _message_role(out[0]) == "system" and _has_cacheable_text(
        _message_content(out[0])
    ):
        system_idx = 0
        cached = _message_to_dict(out[0])
        cached["content"] = _content_with_cache_control(cached.get("content"))
        out[0] = cached

    sliding_idx = _sliding_target_index(out, skip=system_idx)
    if sliding_idx is not None:
        cached = _message_to_dict(out[sliding_idx])
        cached["content"] = _content_with_cache_control(cached.get("content"))
        out[sliding_idx] = cached

    return out, tools
