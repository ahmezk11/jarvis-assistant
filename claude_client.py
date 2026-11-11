"""Claude API backend for Jarvis.

call_claude() runs a manual tool-use loop: Claude decides when to check
weather, tasks, news, etc. (schemas + dispatcher in agent_tools.py), we execute
the calls locally, feed the results back, and return the final text. Manual
rather than the SDK tool runner so Phase 3 can insert confirmation dialogs
before side-effectful tools (email send, calendar writes).
"""

import os

import agent_tools

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

# Shown in the model dropdown alongside local Ollama models
CLAUDE_LABEL = "Claude (cloud)"
CLAUDE_MODEL = "claude-sonnet-5"

_client = None


def is_configured() -> bool:
    return ANTHROPIC_AVAILABLE and bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


# Safety cap on tool round-trips per user turn
MAX_TOOL_ROUNDS = 8


def _create_message(convo: list[dict], system: str, max_tokens: int, tools):
    kwargs = {}
    if tools:
        kwargs["tools"] = tools
    try:
        return _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=convo,
            **kwargs,
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("Anthropic rejected the API key — check ANTHROPIC_API_KEY in .env.")
    except anthropic.RateLimitError:
        raise RuntimeError("Claude is rate-limited right now. Try again in a minute.")
    except anthropic.APIConnectionError:
        raise RuntimeError("Couldn't reach the Anthropic API — check your internet connection.")
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error ({exc.status_code}): {exc.message}")


def call_claude(messages: list[dict], system: str, max_tokens: int = 4096,
                use_tools: bool = True, tool_names: list[str] | None = None) -> str:
    """Send the conversation to Claude, run any tool calls, return the reply text.

    `messages` is the same [{"role": "user"|"assistant", "content": str}] list
    the GUI already keeps. Tool round-trips happen on a local copy — the GUI's
    history stays plain text, so session save/load and Ollama mode are unaffected.
    """
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError(
            "The 'anthropic' package is not installed. Run: pip3 install anthropic"
        )
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    convo = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    tools = agent_tools.get_tools() if use_tools else None
    # Specialist agents run with a narrow slice of the toolset — fewer tools
    # means far more reliable tool selection, especially on smaller models.
    if tools and tool_names:
        allow = set(tool_names)
        tools = [t for t in tools if t["name"] in allow] or tools

    response = _create_message(convo, system, max_tokens, tools)

    for _ in range(MAX_TOOL_ROUNDS):
        if response.stop_reason != "tool_use":
            break
        convo.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": agent_tools.execute_tool(block.name, block.input),
                })
            except agent_tools.ConfirmationDeclined as exc:
                # Ahmed said no — not an error, just report it back plainly.
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(exc),
                })
            except Exception as exc:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tool failed: {exc}",
                    "is_error": True,
                })
        convo.append({"role": "user", "content": results})
        response = _create_message(convo, system, max_tokens, tools)

    # Sonnet 5 runs adaptive thinking by default; skip thinking blocks, keep text.
    return "".join(b.text for b in response.content if b.type == "text").strip()
