"""Free local-model backend for Jarvis, via Ollama.

Mirrors claude_client.call_claude() but runs a local model (default llama3.2)
with a manual tool-use loop, so the web HUD can offer a $0 "Local" brain option
alongside Claude. Tool schemas are the same agent_tools definitions, converted to
Ollama's OpenAI-style function format. Local models are less reliable at tool use
than Claude — that's the tradeoff for free + offline.
"""

import json
import re

import agent_tools

try:
    import ollama
    _AVAILABLE = True
except ImportError:
    ollama = None
    _AVAILABLE = False

# Preference order — strongest tool-capable models first. The best *installed*
# one is chosen at runtime, so pulling a bigger model upgrades Jarvis with no
# code change; llama3.2 remains the always-present fallback.
PREFERRED_MODELS = ["qwen2.5:7b", "qwen2.5", "llama3.1:8b", "llama3.1", "llama3.2"]
MAX_TOOL_ROUNDS = 5

_model_cache: str | None = None


def _installed_models() -> list[str]:
    try:
        resp = ollama.list()
        raw = _msg_get(resp, "models", []) or []
        names = []
        for m in raw:
            n = _msg_get(m, "model", None) or _msg_get(m, "name", None)
            if n:
                names.append(n)
        return names
    except Exception:
        return []


def _pick_model() -> str:
    """Best installed model from the preference list (cached)."""
    global _model_cache
    if _model_cache:
        return _model_cache
    installed = _installed_models()
    for pref in PREFERRED_MODELS:
        base = pref.split(":")[0]
        for name in installed:
            if name == pref or name.startswith(base + ":"):
                _model_cache = name
                return name
    _model_cache = installed[0] if installed else "llama3.2"
    return _model_cache


def reset_model_cache() -> None:
    global _model_cache
    _model_cache = None

# Small local models over-trigger tools; this steers them to chat plainly.
_TOOL_POLICY = (
    "\n\nTool policy: only call a tool when the request genuinely needs live data "
    "or an action — weather, news, web search, calendar, email, tasks, reminders. "
    "For greetings, opinions, or general conversation, reply directly in plain "
    "English. Never output JSON, a function name, or tool syntax as your answer. "
    "When you receive tool results, state the actual returned values in your reply "
    "— never write placeholders like '[inserted by tool call]'.\n"
    "Always answer in English, no matter what.\n"
    "Never claim you performed an action (opening a map, sending a message, "
    "booking something) unless you actually called a tool that did it. If you "
    "cannot do something, say so plainly instead of pretending."
)

# Local models ignore "no markdown" instructions, so strip it deterministically.
_CJK = re.compile(r"[一-鿿぀-ヿ가-힯]")


def _has_cjk(text: str) -> bool:
    return len(_CJK.findall(text or "")) > 3


def _strip_markdown(text: str) -> str:
    t = text or ""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t, flags=re.S)  # **bold**
    t = re.sub(r"__(.+?)__", r"\1", t, flags=re.S)  # __bold__
    t = re.sub(r"`([^`]*)`", r"\1", t)  # `code`
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)  # # headers
    t = t.replace("**", "")  # stray markers
    return t.strip()


def _looks_like_toolcall(text: str) -> bool:
    """A short JSON blob mentioning name/parameters/arguments is almost certainly
    a malformed tool call the small model leaked into its text answer."""
    t = text.strip()
    return (
        t.startswith("{")
        and len(t) < 300
        and any(k in t for k in ('"name"', '"parameters"', '"arguments"', '"function"'))
    )


def is_available() -> bool:
    """True if the ollama library is installed and the daemon answers."""
    if not _AVAILABLE:
        return False
    try:
        ollama.list()
        return True
    except Exception:
        return False


def _msg_get(obj, key, default=None):
    """Read a field from either a dict or an ollama response object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_ollama_tools(claude_tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in claude_tools
    ]


def _finalize(text: str, convo: list[dict], model: str) -> str:
    """Clean a local model's reply: force English (qwen drifts to Chinese) and
    strip markdown it emits despite being told not to."""
    if _has_cjk(text):
        try:
            fix = ollama.chat(
                model=model,
                messages=convo
                + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "Say that again in English only."},
                ],
            )
            retry = (_msg_get(_msg_get(fix, "message"), "content", "") or "").strip()
            if retry and not _has_cjk(retry):
                text = retry
        except Exception:
            pass
    return _strip_markdown(text)


def call_ollama(messages: list[dict], system: str, use_tools: bool = True,
                tool_names: list[str] | None = None) -> str:
    """Run one turn through the local model with tool use; return the reply text."""
    if not _AVAILABLE:
        raise RuntimeError("The 'ollama' package isn't installed. Run: pip3 install ollama")

    model = _pick_model()
    convo = [{"role": "system", "content": system + (_TOOL_POLICY if use_tools else "")}]
    convo += [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    available = agent_tools.get_tools()
    # Specialist agents get a narrow tool slice — small local models pick tools
    # far more reliably from 4 options than from 31.
    if tool_names:
        allow = set(tool_names)
        available = [t for t in available if t["name"] in allow] or available
    tools = _to_ollama_tools(available) if use_tools else None

    for _ in range(MAX_TOOL_ROUNDS):
        resp = ollama.chat(model=model, messages=convo, tools=tools)
        msg = _msg_get(resp, "message")
        content = (_msg_get(msg, "content", "") or "").strip()
        tool_calls = _msg_get(msg, "tool_calls") or []

        if not tool_calls:
            # Small models sometimes leak a fake tool call into the text answer —
            # if so, re-ask without tools for a clean conversational reply.
            if use_tools and _looks_like_toolcall(content):
                retry = ollama.chat(model=model, messages=convo)
                content = (_msg_get(_msg_get(retry, "message"), "content", "") or "").strip()
            return _finalize(content, convo, model)

        # Force one tool at a time. Local models garble parallel tool *results*
        # (they placeholder one), but handle sequential single-tool turns cleanly.
        tool_calls = tool_calls[:1]

        calls, results = [], []
        for tc in tool_calls:
            fn = _msg_get(tc, "function", {}) or {}
            name = _msg_get(fn, "name", "")
            args = _msg_get(fn, "arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            calls.append({"function": {"name": name, "arguments": args}})
            try:
                result = agent_tools.execute_tool(name, args)
            except agent_tools.ConfirmationDeclined as exc:
                result = str(exc)
            except Exception as exc:
                result = f"Tool failed: {exc}"
            results.append({"role": "tool", "content": str(result), "name": name})

        convo.append({"role": "assistant", "content": content, "tool_calls": calls})
        convo.extend(results)

    # Ran out of tool rounds — ask once more for a plain answer.
    resp = ollama.chat(model=model, messages=convo)
    final = (_msg_get(_msg_get(resp, "message"), "content", "") or "").strip()
    return _finalize(final, convo, model)
