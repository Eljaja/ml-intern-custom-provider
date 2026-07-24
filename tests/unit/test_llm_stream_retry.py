"""Mid-stream failure handling in _call_llm_streaming.

The stream used to be consumed after the retry loop had already broken out, so a
read timeout part-way through a response killed the turn even when the request
itself was retryable.
"""

import asyncio
from types import SimpleNamespace

import pytest

from agent.core import agent_loop


class _Chunk:
    """Minimal stand-in for a litellm streaming chunk."""

    def __init__(self, content=None, finish_reason=None, usage=None, tool_call=None):
        delta = SimpleNamespace(content=content, tool_calls=tool_call)
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = usage


def _usage(total=42):
    return SimpleNamespace(total_tokens=total)


class _Stream:
    """Async iterator that yields chunks, optionally raising part-way through."""

    def __init__(self, chunks, raise_after=None, error=None):
        self._chunks = list(chunks)
        self._raise_after = raise_after
        self._error = error or ConnectionError("stream dropped")
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise_after is not None and self._i == self._raise_after:
            raise self._error
        if self._i >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._i]
        self._i += 1
        return chunk


def _session(monkeypatch):
    events = []

    async def send_event(event):
        events.append(event)

    session = SimpleNamespace(
        is_cancelled=False,
        _cancelled=asyncio.Event(),
        config=SimpleNamespace(model_name="anthropic/claude-opus-4-7"),
        hf_token=None,
        send_event=send_event,
        events=events,
    )
    return session


@pytest.fixture(autouse=True)
def _no_env_context(monkeypatch):
    class FakeEnv:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr(
        agent_loop, "use_custom_inference_openai_key_env", lambda *_a, **_k: FakeEnv()
    )
    monkeypatch.setattr(agent_loop, "_retry_delay_for", lambda _e, _a: 0)
    monkeypatch.setattr(
        agent_loop.telemetry, "record_llm_call", _record_llm_call_stub()
    )


def _record_llm_call_stub():
    async def _stub(*_a, **_k):
        return {}

    return _stub


@pytest.mark.asyncio
async def test_failure_before_any_chunk_is_retried(monkeypatch):
    session = _session(monkeypatch)
    attempts = []

    async def fake_acompletion(**_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("connection reset")
        return _Stream(
            [_Chunk(content="hello"), _Chunk(finish_reason="stop", usage=_usage())]
        )

    monkeypatch.setattr(agent_loop, "acompletion", fake_acompletion)

    result = await agent_loop._call_llm_streaming(
        session, [{"role": "user", "content": "hi"}], None, {"model": "m"}
    )

    assert len(attempts) == 2
    assert result.content == "hello"


@pytest.mark.asyncio
async def test_failure_mid_stream_is_retried_when_nothing_was_emitted(monkeypatch):
    """A drop during the pre-content phase is still safe to retry."""
    session = _session(monkeypatch)
    attempts = []

    async def fake_acompletion(**_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            # Chunk with no content, then a failure: nothing reached the client.
            return _Stream([_Chunk(content=None)], raise_after=1)
        return _Stream(
            [_Chunk(content="recovered"), _Chunk(finish_reason="stop", usage=_usage())]
        )

    monkeypatch.setattr(agent_loop, "acompletion", fake_acompletion)

    result = await agent_loop._call_llm_streaming(
        session, [{"role": "user", "content": "hi"}], None, {"model": "m"}
    )

    assert len(attempts) == 2
    assert result.content == "recovered"


@pytest.mark.asyncio
async def test_failure_after_emitting_content_is_not_retried(monkeypatch):
    """Retrying would replay text the user can already see."""
    session = _session(monkeypatch)
    attempts = []

    async def fake_acompletion(**_kwargs):
        attempts.append(1)
        return _Stream([_Chunk(content="partial ")], raise_after=1)

    monkeypatch.setattr(agent_loop, "acompletion", fake_acompletion)

    with pytest.raises(ConnectionError):
        await agent_loop._call_llm_streaming(
            session, [{"role": "user", "content": "hi"}], None, {"model": "m"}
        )

    assert len(attempts) == 1
    emitted = [e for e in session.events if e.event_type == "assistant_chunk"]
    assert [e.data["content"] for e in emitted] == ["partial "]


@pytest.mark.asyncio
async def test_retry_does_not_concatenate_partial_responses(monkeypatch):
    """Accumulators must reset per attempt, or the retry appends to leftovers."""
    session = _session(monkeypatch)
    attempts = []

    async def fake_acompletion(**_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            # Tool-call fragment then failure, with no content emitted.
            tool_call = [
                SimpleNamespace(
                    index=0,
                    id="call_1",
                    function=SimpleNamespace(name="bash", arguments='{"cmd'),
                )
            ]
            return _Stream([_Chunk(tool_call=tool_call)], raise_after=1)
        tool_call = [
            SimpleNamespace(
                index=0,
                id="call_2",
                function=SimpleNamespace(name="bash", arguments='{"cmd": "ls"}'),
            )
        ]
        return _Stream(
            [_Chunk(tool_call=tool_call), _Chunk(finish_reason="tool_calls")]
        )

    monkeypatch.setattr(agent_loop, "acompletion", fake_acompletion)

    result = await agent_loop._call_llm_streaming(
        session, [{"role": "user", "content": "hi"}], None, {"model": "m"}
    )

    assert len(attempts) == 2
    assert result.tool_calls_acc[0]["id"] == "call_2"
    assert result.tool_calls_acc[0]["function"]["arguments"] == '{"cmd": "ls"}'


@pytest.mark.asyncio
async def test_retry_backoff_wakes_early_on_cancel(monkeypatch):
    """Stop should not appear to hang for the whole backoff."""
    session = _session(monkeypatch)
    session._cancelled.set()
    session.is_cancelled = True

    slept = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(agent_loop.asyncio, "sleep", fake_sleep)

    assert await agent_loop._sleep_or_cancel(session, 30) is True
    assert slept == []


@pytest.mark.asyncio
async def test_sleep_or_cancel_returns_false_after_a_quiet_backoff(monkeypatch):
    session = _session(monkeypatch)
    assert await agent_loop._sleep_or_cancel(session, 0.01) is False
