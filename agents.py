"""EDITH's specialist agent network.

A multi-agent orchestration layer: instead of one assistant juggling all 31
tools, a router decomposes a request into sub-tasks and hands each to a
specialist that runs with its own system prompt and a *narrow* slice of the
toolset. Independent sub-tasks run in parallel; EDITH then synthesises the
results into one answer.

Why the narrow tool slices matter: tool-selection accuracy falls off sharply as
the tool count grows, especially on small local models. An agent choosing among
5 tools is far more reliable than one choosing among 31 — that specialisation is
the actual mechanism here, not a stylistic flourish.

Public surface:
    AGENTS                     the roster (id → spec)
    activity()                 live per-agent status, for the HUD graph
    run_agent(id, task, ...)   run one specialist
    dispatch(request, ...)     route → run (parallel) → synthesise
"""

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import agent_tools
import claude_client
import memory_manager
import ollama_client

MAX_PARALLEL = 4


# ── The roster ────────────────────────────────────────────────────────────
# Chosen for what a *personal* assistant actually does day to day. Each agent
# owns one domain and only the tools for that domain.

AGENTS: dict[str, dict] = {
    "inbox": {
        "label": "Inbox",
        "description": "Email — reading, searching, triaging and drafting Gmail.",
        "tools": ["list_unread_emails", "search_emails", "read_email", "draft_email", "send_email"],
        "system": (
            "You are the Inbox specialist. You handle email only. Triage into "
            "URGENT / ACTION / FYI / SKIP when asked to review mail. Only write "
            "a draft when Ahmed has actually asked you to write or reply to "
            "something — a question about his mail is answered by reading, not "
            "by composing. When he does ask, draft in his voice: professional "
            "but warm, concise, and save it rather than sending."
        ),
    },
    "scheduler": {
        "label": "Scheduler",
        "description": "Calendar — checking the schedule, creating and cancelling events, reminders.",
        "tools": ["list_calendar_events", "create_calendar_event", "delete_calendar_event",
                  "get_current_time", "set_reminder"],
        "system": (
            "You are the Scheduler specialist. You handle the calendar and "
            "reminders only. Times are Asia/Dubai (+04:00) — always use ISO 8601 "
            "with that offset. Check for conflicts before proposing a new slot."
        ),
    },
    "researcher": {
        "label": "Researcher",
        "description": "Looking things up — web search, news, current events, facts, prices.",
        "tools": ["web_search", "get_news", "get_current_time"],
        "system": (
            "You are the Research specialist. Search the web for anything "
            "time-sensitive or factual rather than answering from memory. Report "
            "findings concisely and say where they came from. Never guess at "
            "current events, scores or prices."
        ),
    },
    "taskmaster": {
        "label": "Taskmaster",
        "description": "To-do list — adding, listing, completing and clearing tasks.",
        "tools": ["add_task", "list_tasks", "complete_task", "delete_task",
                  "clear_completed_tasks", "done_today"],
        "system": (
            "You are the Task specialist. You manage Ahmed's to-do list only. "
            "Break vague intentions into concrete, actionable task text. Set "
            "priority high only when genuinely urgent."
        ),
    },
    "archivist": {
        "label": "Archivist",
        "description": "Documents and long-term memory — Drive, Notion, and remembering facts.",
        "tools": ["search_drive", "read_drive_file", "create_drive_doc",
                  "search_notion", "read_notion_page", "create_notion_page",
                  "remember", "recall", "forget"],
        "system": (
            "You are the Archivist. You handle documents (Drive, Notion) and "
            "EDITH's long-term memory. When you learn a durable fact about "
            "Ahmed, save it with the remember tool. Quote source documents "
            "accurately — never paraphrase a fact into something it didn't say."
        ),
    },
    "operator": {
        "label": "Operator",
        "description": "The local machine and surroundings — system stats, apps, maps, weather.",
        "tools": ["get_system_stats", "open_app", "open_map", "get_weather", "get_current_time"],
        "system": (
            "You are the Operator. You handle the local machine and physical "
            "surroundings: system diagnostics, launching apps, maps and "
            "directions, weather. Default to Dubai for location questions."
        ),
    },
}


# ── Live activity (drives the HUD's network graph) ────────────────────────

_activity: dict[str, str] = {a: "idle" for a in AGENTS}
_activity_lock = threading.Lock()


def _set_state(agent_id: str, state: str) -> None:
    with _activity_lock:
        _activity[agent_id] = state


def activity() -> dict[str, str]:
    with _activity_lock:
        return dict(_activity)


def reset_activity() -> None:
    with _activity_lock:
        for a in _activity:
            _activity[a] = "idle"


def roster() -> list[dict]:
    return [
        {"id": a, "label": s["label"], "description": s["description"],
         "tools": s["tools"], "tool_count": len(s["tools"])}
        for a, s in AGENTS.items()
    ]


# ── Brain routing ─────────────────────────────────────────────────────────

def _call(messages, system, backend, tool_names=None, use_tools=True) -> str:
    if backend == "local":
        return ollama_client.call_ollama(messages, system=system,
                                         use_tools=use_tools, tool_names=tool_names)
    return claude_client.call_claude(messages, system=system,
                                     use_tools=use_tools, tool_names=tool_names)


def run_agent(agent_id: str, task: str, backend: str = "local") -> str:
    """Run one specialist on one sub-task, with only its own tools."""
    spec = AGENTS.get(agent_id)
    if not spec:
        return f"Unknown agent: {agent_id}"
    _set_state(agent_id, "running")
    try:
        system = (
            f"{spec['system']}\n\nYou are one specialist in EDITH's agent network, "
            "working for Ahmed in Dubai. Do only your part of the task and report "
            "the result plainly in a few sentences — no markdown, no preamble. "
            "If the task isn't yours to do, say so briefly instead of guessing.\n\n"
            "Read-only by default: if the task is a question ('how many…', "
            "'what's on…', 'do I have…'), answer it by looking things up. Only "
            "take an action that changes something — sending or drafting mail, "
            "creating or deleting events, writing documents — when the task "
            "explicitly asks for that action. Never invent extra work."
        )
        out = _call([{"role": "user", "content": task}], system, backend,
                    tool_names=spec["tools"])
        _set_state(agent_id, "done")
        return (out or "").strip() or "(no result)"
    except Exception as exc:
        _set_state(agent_id, "error")
        return f"{spec['label']} failed: {exc}"


# ── Planner ───────────────────────────────────────────────────────────────

_KEYWORDS = {
    "inbox": r"\b(email|mail|inbox|unread|reply|draft|message from)\b",
    "scheduler": r"\b(calendar|schedule|meeting|event|appointment|remind|free time|busy)\b",
    "researcher": r"\b(search|look up|find out|news|latest|current|who is|what is|price|score)\b",
    "taskmaster": r"\b(task|todo|to-do|reminder list|my list|add .* list)\b",
    "archivist": r"\b(document|doc|drive|notion|note|remember|memory|file)\b",
    "operator": r"\b(weather|cpu|memory|battery|system|open |launch|map|directions|temperature)\b",
}


def _fallback_plan(request: str) -> list[dict]:
    """Keyword routing — used when the model's JSON plan can't be parsed."""
    hits = [a for a, pat in _KEYWORDS.items() if re.search(pat, request, re.I)]
    if not hits:
        hits = ["researcher"]
    return [{"agent": a, "task": request} for a in hits[:MAX_PARALLEL]]


def plan(request: str, backend: str = "local") -> list[dict]:
    """Decompose a request into {agent, task} steps."""
    catalog = "\n".join(f"- {a}: {s['description']}" for a, s in AGENTS.items())
    prompt = (
        f"Available specialists:\n{catalog}\n\n"
        f"Ahmed's request: \"{request}\"\n\n"
        "Break this into the fewest sub-tasks that cover it, assigning each to one "
        "specialist. Reply with ONLY a minified JSON array, no prose:\n"
        '[{"agent":"<id>","task":"<what that specialist should do>"}]\n'
        "Use one entry if a single specialist covers it. Maximum 4 entries."
    )
    try:
        raw = _call([{"role": "user", "content": prompt}],
                    "You are a task router. Output only a valid minified JSON array.",
                    backend, use_tools=False)
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            parsed = json.loads(m.group(0))
            steps = [
                {"agent": s["agent"], "task": str(s.get("task") or request)}
                for s in parsed
                if isinstance(s, dict) and s.get("agent") in AGENTS
            ][:MAX_PARALLEL]
            if steps:
                return steps
    except Exception:
        pass
    return _fallback_plan(request)


# ── Dispatch: route → run in parallel → synthesise ────────────────────────

def dispatch(request: str, backend: str = "local", synthesise: bool = True) -> dict:
    """Full multi-agent run. Returns {plan, results, summary}."""
    reset_activity()
    steps = plan(request, backend)
    for s in steps:
        _set_state(s["agent"], "queued")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {
            pool.submit(run_agent, s["agent"], s["task"], backend): s for s in steps
        }
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                output = fut.result()
            except Exception as exc:
                output = f"failed: {exc}"
            results.append({"agent": s["agent"], "label": AGENTS[s["agent"]]["label"],
                            "task": s["task"], "output": output})

    # Keep results in the planned order for a readable summary.
    order = {s["agent"]: i for i, s in enumerate(steps)}
    results.sort(key=lambda r: order.get(r["agent"], 99))

    summary = ""
    if synthesise:
        if len(results) == 1:
            summary = results[0]["output"]
        else:
            joined = "\n\n".join(f"{r['label']}: {r['output']}" for r in results)
            try:
                summary = _call(
                    [{"role": "user", "content":
                      f"Ahmed asked: \"{request}\"\n\nYour specialists reported:\n\n{joined}\n\n"
                      "Combine these into one short, natural answer for Ahmed. Plain prose, "
                      "no markdown or lists. Don't mention the specialists by name."}],
                    memory_manager.build_claude_system_prompt(memory_manager.load()),
                    backend, use_tools=False,
                ).strip()
            except Exception:
                summary = joined
    return {"plan": steps, "results": results, "summary": summary or ""}
