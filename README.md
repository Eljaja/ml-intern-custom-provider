<p align="center">
  <img src="frontend/public/smolagents.webp" alt="smolagents logo" width="160" />
</p>

<p align="center">
    <a href="https://github.com/Eljaja/ml-intern-custom-provider/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
    <a href="https://smolagents-ml-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-ml-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

# ML Intern

An ML intern that autonomously researches, writes, and ships good quality ML related code using the Hugging Face ecosystem — with deep access to docs, papers, datasets, and cloud compute.

> A fork of [huggingface/ml-intern](https://github.com/huggingface/ml-intern).
> On top of upstream it adds: routing chosen models to a private
> OpenAI-compatible endpoint (`CUSTOM_INFERENCE_*`, see below), a Zulip
> notification gateway, a self-hosted Docker Compose stack, and procedural
> skills the agent writes for itself. Upstream has since moved all inference
> behind the HF Router; this fork keeps direct Anthropic/Bedrock and custom
> endpoints, so the two have diverged on model routing.

## Quick Start

### Installation

```bash
git clone git@github.com:Eljaja/ml-intern-custom-provider.git
cd ml-intern-custom-provider
uv sync
uv tool install -e .
```

#### That's it. Now `ml-intern` works from any directory:

```bash
ml-intern
```

Create a `.env` file in the project root (or export these in your shell):

```bash
ANTHROPIC_API_KEY=<your-anthropic-api-key> # if using anthropic models
OPENAI_API_KEY=<your-openai-api-key> # if using openai models
LOCAL_LLM_BASE_URL=http://localhost:8000 # shared fallback for local model prefixes
LOCAL_LLM_API_KEY=<optional-local-api-key> # optional shared local API key
HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token> 
```
If no `HF_TOKEN` is set, the CLI will prompt you to paste one on first launch
unless you start on a local model. To get a GITHUB_TOKEN follow the tutorial
[here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).

**Custom OpenAI-compatible LLM (optional):** to send specific models to a private endpoint (not the Hugging Face router), set in `.env`:

```bash
CUSTOM_INFERENCE_API_BASE=https://your-host.example/v1
CUSTOM_INFERENCE_API_KEY=sk-...
# Comma-separated model base ids; if omitted, defaults to minimax/minimax-m2.7
# CUSTOM_INFERENCE_MODEL=minimax/minimax-m2.7
```

Use the same id with `--model` or `model_name` in `configs/main_agent_config.json`. Other `org/model` names continue to use the HF router unless listed in `CUSTOM_INFERENCE_MODEL`.

When the **active** `model_name` is routed to `CUSTOM_INFERENCE_*`, a **Hugging Face token is not required** to start the CLI (Hub tools, datasets, and MCP may still need `HF_TOKEN` to work). Otherwise set `HF_TOKEN` as above.

### Usage

**Interactive mode** (start a chat session):

```bash
ml-intern
```

**Headless mode** (single prompt, auto-approve):

```bash
ml-intern "fine-tune llama on my dataset"
```

**Options:**

```bash
ml-intern --model anthropic/claude-opus-4-7 "your prompt"   # requires ANTHROPIC_API_KEY
ml-intern --model openai/gpt-5.5 "your prompt"              # requires OPENAI_API_KEY
ml-intern --model ollama/llama3.1:8b "your prompt"
ml-intern --model vllm/meta-llama/Llama-3.1-8B-Instruct "your prompt"
ml-intern --sandbox-tools "your prompt"                         # use HF Space sandbox tools
ml-intern --max-iterations 100 "your prompt"
ml-intern --no-stream "your prompt"
```

Run `ml-intern` then `/model` to see the full list of suggested model ids
(Claude, GPT, HF-router models like MiniMax, Kimi, GLM, DeepSeek, and local
model prefixes).

**Local models:**

Local model support uses OpenAI-compatible HTTP endpoints through LiteLLM. The
agent does not load model weights directly from disk; start your inference
server first, then select it with a provider-specific model prefix:

```bash
ml-intern --model ollama/llama3.1:8b "your prompt"
ml-intern --model vllm/meta-llama/Llama-3.1-8B-Instruct "your prompt"
```

Inside interactive mode, switch with `/model`:

```text
/model ollama/llama3.1:8b
/model lm_studio/google/gemma-3-4b
/model llamacpp/llama-3.1-8b-instruct
```

Supported local prefixes are `ollama/`, `vllm/`, `lm_studio/`, and
`llamacpp/`. Set `LOCAL_LLM_BASE_URL` and optional `LOCAL_LLM_API_KEY` to use
one shared local endpoint, or override a specific provider with its matching
`*_BASE_URL` / `*_API_KEY` variable, such as `OLLAMA_BASE_URL` or
`VLLM_API_KEY`. Provider-specific variables take precedence over the shared
local variables. Base URLs may include or omit `/v1`.

**CLI tool runtime:**

By default, the CLI runs `bash`, `read`, `write`, and `edit` on your local
filesystem. To use HF Space sandbox tools instead, including `sandbox_create`,
opt in with `--sandbox-tools`:

```bash
ml-intern --sandbox-tools "test this training script in a GPU sandbox"
ml-intern --model llamacpp/ggml-org/gemma-3-1b-it-GGUF --sandbox-tools
```

Sandbox tool runtime requires `HF_TOKEN`, even when the selected model is local,
because it creates private HF Spaces. You can also make sandbox tools your CLI
default in `~/.config/ml-intern/cli_agent_config.json`:

```json
{ "tool_runtime": "sandbox" }
```

Use the default local runtime when you want tools to inspect or edit files in
your checkout. Use sandbox runtime when you want the agent to create or replace
an HF Space sandbox, test code remotely, or request GPU sandbox hardware before
launching larger HF Jobs.

## Sharing Traces

Every session is auto-uploaded to your **own private Hugging Face dataset**
in [Claude Code JSONL format](https://huggingface.co/changelog/agent-trace-viewer),
which the HF Agent Trace Viewer auto-detects so you can browse turns, tool
calls, and model responses directly on the Hub.

By default the dataset is named `{your-hf-username}/ml-intern-sessions` and is
**created private**. You can flip it to public from inside the CLI:

```bash
/share-traces            # show current visibility + dataset URL
/share-traces public     # publish (anyone can view)
/share-traces private    # lock it back down
```

You can also flip visibility from the dataset page on huggingface.co — the
agent honours whatever you set there for subsequent uploads.

To opt out entirely, set in your CLI config (e.g. `configs/cli_agent_config.json`
or `~/.config/ml-intern/cli_agent_config.json`):

```json
{ "share_traces": false }
```

To override the destination repo, set:

```json
{ "personal_trace_repo_template": "{hf_user}/my-custom-traces" }
```

The shared `smolagents/ml-intern-sessions` dataset is unrelated and only
receives anonymized telemetry rows used by the backend KPI scheduler.

## Supported Gateways

One-way notification gateways: they send out-of-band status updates on
approval-required, error and turn-complete events, and do not accept inbound
chat messages. Slack and Zulip are both available, from CLI and web sessions
alike.

### Slack

Slack notifications use the Slack Web API to post messages when the agent needs
approval, hits an error, or completes a turn. Create a Slack app with a bot token
that has `chat:write`, invite the bot to the target channel, then set:

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
```

The CLI automatically creates a `slack.default` destination when both variables
are present. Optional environment variables for the env-only default:

```bash
ML_INTERN_SLACK_NOTIFICATIONS=false
ML_INTERN_SLACK_DESTINATION=slack.ops
ML_INTERN_SLACK_AUTO_EVENTS=approval_required,error,turn_complete
ML_INTERN_SLACK_ALLOW_AGENT_TOOL=true
ML_INTERN_SLACK_ALLOW_AUTO_EVENTS=true
```

For a persistent user-level config, put overrides in
`~/.config/ml-intern/cli_agent_config.json` or point `ML_INTERN_CLI_CONFIG` at a
JSON file:

```json
{
  "messaging": {
    "enabled": true,
    "auto_event_types": ["approval_required", "error", "turn_complete"],
    "destinations": {
      "slack.ops": {
        "provider": "slack",
        "token": "${SLACK_BOT_TOKEN}",
        "channel": "${SLACK_CHANNEL_ID}",
        "allow_agent_tool": true,
        "allow_auto_events": true
      }
    }
  }
}
```

### Zulip

Zulip notifications post to a stream (or a private message) on the same events.
Create a bot in your Zulip organisation, then set:

```bash
ZULIP_SITE=https://chat.example.com
ZULIP_BOT_EMAIL=ml-intern-bot@example.com
ZULIP_API_KEY=...
ZULIP_STREAM=ml-agent
```

A `zulip.default` destination is created automatically once site, bot email, API
key and a target are all present. Optional variables mirror the Slack ones:

```bash
ML_INTERN_ZULIP_NOTIFICATIONS=false
ML_INTERN_ZULIP_DESTINATION=zulip.ops
ML_INTERN_ZULIP_AUTO_EVENTS=approval_required,error,turn_complete
ML_INTERN_ZULIP_ALLOW_AGENT_TOOL=true
ML_INTERN_ZULIP_ALLOW_AUTO_EVENTS=true
```

For private messages instead of a stream:

```bash
ZULIP_MESSAGE_TYPE=private
ZULIP_TO=user@example.com
```

Both gateways are configured the same way and by the same code path
(`agent/config.py`, `_ENV_PROVIDERS`), and both apply to CLI *and* web sessions.
An explicit destination of the same name in a JSON config always wins over the
environment.

## Self-hosted stack (Docker Compose)

```bash
cp .env.example .env      # fill in the keys you need
docker compose up --build
```

Then open <http://localhost:8080>. With GPUs:

```bash
docker compose -f docker-compose.yaml -f docker-compose.gpu.yaml up --build
```

What the stack gives you, and what it assumes:

- MongoDB for chat sessions, plus named volumes so the agent's workspace, its
  learned skills and local trajectory backups survive `--build`.
- `AGENT_LOCAL_MODE=1` — the agent runs `bash`/`read`/`write` **inside the
  backend container**, not in a remote sandbox.
- No `OAUTH_CLIENT_ID`, so authentication is off and every caller is served as
  the `dev` user.

Those last two together mean anyone who can reach the port can run commands and
read the API keys out of the container environment. Both published ports are
therefore bound to `127.0.0.1`, and `backend/runtime_guard.py` refuses to boot
unless `ML_INTERN_ALLOW_UNAUTHENTICATED_LOCAL_MODE=1` acknowledges it. To serve
this to other machines, configure HF OAuth and drop the acknowledgement — do not
widen the port bindings.

## Procedural skills

In local mode (CLI, or the web backend with `AGENT_LOCAL_MODE=1`) the agent keeps
a per-user store of reusable procedures under `ML_INTERN_SKILLS_DIR`, one
`SKILL.md` per skill with YAML frontmatter.

- `skills_list` / `skill_view` / `skill_manage` let the agent read and write them.
  Registered only in local mode — the store is backed by a filesystem the hosted
  sandbox deployment does not durably own.
- The descriptions of enabled skills ride in the system prompt (capped at 40,
  most recently used first) so the agent knows what exists without a tool call.
- After a successful turn that used at least two tools, a low-effort reflection
  call decides whether to save or amend a skill. It runs detached from the turn
  and is reported as `kind="skill_reflection"` in telemetry. Set
  `"skill_reflection": false` in the agent config to switch it off.
- Skills are secret-scrubbed (`agent/core/redact.py`) and size-capped on write.
  Manage them from the sidebar panel: view, enable/disable, delete.


## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         User/CLI                            │
└────────────┬─────────────────────────────────────┬──────────┘
             │ Operations                          │ Events
             ↓ (user_input, exec_approval,         ↑
      submission_queue  interrupt, compact, ...)  event_queue
             │                                          │
             ↓                                          │
┌────────────────────────────────────────────────────┐  │
│            submission_loop (agent_loop.py)         │  │
│  ┌──────────────────────────────────────────────┐  │  │
│  │  1. Receive Operation from queue             │  │  │
│  │  2. Route to handler (run_agent/compact/...) │  │  │
│  └──────────────────────────────────────────────┘  │  │
│                      ↓                             │  │
│  ┌──────────────────────────────────────────────┐  │  │
│  │         Handlers.run_agent()                 │  ├──┤
│  │                                              │  │  │
│  │  ┌────────────────────────────────────────┐  │  │  │
│  │  │  Agentic Loop (max 300 iterations)     │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  ┌──────────────────────────────────┐  │  │  │  │
│  │  │  │ Session                          │  │  │  │  │
│  │  │  │  ┌────────────────────────────┐  │  │  │  │  │
│  │  │  │  │ ContextManager             │  │  │  │  │  │
│  │  │  │  │ • Message history          │  │  │  │  │  │
│  │  │  │  │   (litellm.Message[])      │  │  │  │  │  │
│  │  │  │  │ • Auto-compaction (170k)   │  │  │  │  │  │
│  │  │  │  │ • Session upload to HF     │  │  │  │  │  │
│  │  │  │  └────────────────────────────┘  │  │  │  │  │
│  │  │  │                                  │  │  │  │  │
│  │  │  │  ┌────────────────────────────┐  │  │  │  │  │
│  │  │  │  │ ToolRouter                 │  │  │  │  │  │
│  │  │  │  │  ├─ HF docs & research     │  │  │  │  │  │
│  │  │  │  │  ├─ HF repos, datasets,    │  │  │  │  │  │
│  │  │  │  │  │  jobs, papers           │  │  │  │  │  │
│  │  │  │  │  ├─ GitHub code search     │  │  │  │  │  │
│  │  │  │  │  ├─ Sandbox & local tools  │  │  │  │  │  │
│  │  │  │  │  ├─ Planning               │  │  │  │  │  │
│  │  │  │  │  └─ MCP server tools       │  │  │  │  │  │
│  │  │  │  └────────────────────────────┘  │  │  │  │  │
│  │  │  └──────────────────────────────────┘  │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  ┌──────────────────────────────────┐  │  │  │  │
│  │  │  │ Doom Loop Detector               │  │  │  │  │
│  │  │  │ • Detects repeated tool patterns │  │  │  │  │
│  │  │  │ • Injects corrective prompts     │  │  │  │  │
│  │  │  └──────────────────────────────────┘  │  │  │  │
│  │  │                                        │  │  │  │
│  │  │  Loop:                                 │  │  │  │
│  │  │    1. LLM call (litellm.acompletion)   │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    2. Parse tool_calls[]               │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    3. Approval check                   │  │  │  │
│  │  │       (jobs, sandbox, destructive ops) │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    4. Execute via ToolRouter           │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    5. Add results to ContextManager    │  │  │  │
│  │  │       ↓                                │  │  │  │
│  │  │    6. Repeat if tool_calls exist       │  │  │  │
│  │  └────────────────────────────────────────┘  │  │  │
│  └──────────────────────────────────────────────┘  │  │
└────────────────────────────────────────────────────┴──┘
```

### Agentic Loop Flow

```
User Message
     ↓
[Add to ContextManager]
     ↓
     ╔═══════════════════════════════════════════╗
     ║      Iteration Loop (max 300)             ║
     ║                                           ║
     ║  Get messages + tool specs                ║
     ║         ↓                                 ║
     ║  litellm.acompletion()                    ║
     ║         ↓                                 ║
     ║  Has tool_calls? ──No──> Done             ║
     ║         │                                 ║
     ║        Yes                                ║
     ║         ↓                                 ║
     ║  Add assistant msg (with tool_calls)      ║
     ║         ↓                                 ║
     ║  Doom loop check                          ║
     ║         ↓                                 ║
     ║  For each tool_call:                      ║
     ║    • Needs approval? ──Yes──> Wait for    ║
     ║    │                         user confirm ║
     ║    No                                     ║
     ║    ↓                                      ║
     ║    • ToolRouter.execute_tool()            ║
     ║    • Add result to ContextManager         ║
     ║         ↓                                 ║
     ║  Continue loop ─────────────────┐         ║
     ║         ↑                       │         ║
     ║         └───────────────────────┘         ║
     ╚═══════════════════════════════════════════╝
```

## Events

The agent emits the following events via `event_queue`:

- `processing` - Starting to process user input
- `ready` - Agent is ready for input
- `assistant_chunk` - Streaming token chunk
- `assistant_message` - Complete LLM response text
- `assistant_stream_end` - Token stream finished
- `tool_call` - Tool being called with arguments
- `tool_output` - Tool execution result
- `tool_log` - Informational tool log message
- `tool_state_change` - Tool execution state transition
- `approval_required` - Requesting user approval for sensitive operations
- `turn_complete` - Agent finished processing
- `error` - Error occurred during processing
- `interrupted` - Agent was interrupted
- `compacted` - Context was compacted
- `undo_complete` - Undo operation completed
- `shutdown` - Agent shutting down

## Development

### Pre-commit Checks

Run Ruff and the test suite before every commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

If the format check fails, run `uv run ruff format .` and re-run the checks
before committing. Lint rules live in `[tool.ruff.lint]` in `pyproject.toml`;
every `ignore` there carries the reason it is ignored.

The frontend is checked separately, and CI runs the same three commands:

```bash
cd frontend && npm ci && npm run lint && npm run build
```

`npm run build` is `tsc -b && vite build`, so it is also the typecheck.

Three tests fail on Windows for environment reasons (`fcntl` is POSIX-only,
plus a path-separator and a file-encoding assumption). They pass on the Linux
CI runners.

### Adding Built-in Tools

Edit `agent/core/tools.py`:

```python
def create_builtin_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="your_tool",
            description="What your tool does",
            parameters={
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "Parameter description"}
                },
                "required": ["param"]
            },
            handler=your_async_handler
        ),
        # ... existing tools
    ]
```

### Adding MCP Servers

Edit `configs/cli_agent_config.json` for CLI defaults, or
`configs/frontend_agent_config.json` for web-session defaults:

```json
{
  "model_name": "anthropic/claude-sonnet-4-5-20250929",
  "mcpServers": {
    "your-server-name": {
      "transport": "http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${YOUR_TOKEN}"
      }
    }
  }
}
```

Note: Environment variables like `${YOUR_TOKEN}` are auto-substituted from `.env`.

## Cite ml-intern
If you use `ml-intern` in your work, please cite it by using the following BibTeX entry or similar.
```bibtex
@Misc{ml-intern,
  title =        {ml-intern: an agent that autonomously researches, writes, and ships good quality ML related code using the Hugging Face ecosystem},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/huggingface/ml-intern}},
  year =         {2026}
}
```
