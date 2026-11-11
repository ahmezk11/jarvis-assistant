"""Claude tool definitions + dispatcher for Jarvis.

Each entry in TOOLS is a Claude tool schema; execute_tool() runs the matching
Python function from tools.py / task_manager.py and returns a plain string for
the tool_result. The GUI injects context (memory, reminder popups) via
set_context() so this module never imports jarvis.py.
"""

import config
import task_manager
import google_integration as google
import notion_integration as notion
from tools import (
    get_weather, format_weather,
    get_news,
    get_system_stats, format_system_stats,
    web_search, format_search_results,
    set_reminder, open_app, get_current_time,
)

_memory: dict = {}
_reminder_cb = None   # fn(text) — set by the GUI so reminders surface as toasts
_confirm_cb = None    # fn(title, detail) -> bool — GUI modal before side-effects
_backend = "local"    # brain the current turn is using; delegated agents inherit
                      # it so a free-local chat never silently spends credits


def set_backend(backend: str) -> None:
    global _backend
    _backend = backend if backend in ("local", "claude") else "local"


def set_context(memory: dict, reminder_callback=None, confirm_callback=None):
    global _memory, _reminder_cb, _confirm_cb
    _memory = memory
    _reminder_cb = reminder_callback
    _confirm_cb = confirm_callback


class ConfirmationDeclined(Exception):
    """Raised when Ahmed declines a side-effectful action's confirmation dialog."""


def _confirm(title: str, detail: str) -> None:
    """Block on the GUI confirmation dialog before a send/create/delete.

    Fail-closed: if no confirm callback is wired (e.g. headless), the action is
    declined rather than silently executed.
    """
    if _confirm_cb is None or not _confirm_cb(title, detail):
        raise ConfirmationDeclined(
            "Ahmed did not confirm — nothing was sent or changed."
        )


# ── Tool schemas ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_current_time",
        "description": "Get the current local date and time. Call this when the user asks the time, the date, or what day it is.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather",
        "description": "Get current weather conditions for a city. Call this when the user asks about the weather. If no city is given, omit it — the user's home city is used.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Dubai'. Omit to use the user's home city."},
            },
        },
    },
    {
        "name": "get_news",
        "description": "Get top news headlines. Call this when the user asks for news or headlines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["general", "technology", "science", "health", "business", "sports"],
                    "description": "Headline category. Omit for the user's default.",
                },
                "count": {"type": "integer", "description": "Number of headlines (default 3)."},
            },
        },
    },
    {
        "name": "get_system_stats",
        "description": "Get this computer's CPU, RAM, battery, and uptime. Call this when the user asks how the system or machine is doing.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web and return raw results for you to synthesize. Call this when the answer depends on current information you don't reliably know — recent events, prices, versions, or anything the user flags as time-sensitive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "set_reminder",
        "description": "Set a local reminder that pops up on screen after a delay. Call this when the user asks to be reminded of something.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to remind the user about."},
                "minutes": {"type": "integer", "description": "Minutes from now to fire the reminder."},
            },
            "required": ["message", "minutes"],
        },
    },
    {
        "name": "open_app",
        "description": "Open an application on the user's computer by name, e.g. 'Safari' or 'Spotify'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "The application name."},
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "delegate",
        "description": "Hand a multi-part or complex request to your specialist agent network (inbox, scheduler, researcher, taskmaster, archivist, operator). They work in parallel and report back. Use this when a request spans several domains at once — e.g. 'check my mail, my calendar and the weather' — rather than doing each yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "The full request to decompose across specialists."},
            },
            "required": ["request"],
        },
    },
    {
        "name": "remember",
        "description": "Save a durable fact about Ahmed to long-term memory so you still know it in future conversations — preferences, people, dates, constraints, ongoing projects. Call this whenever he tells you something worth remembering, without being asked to.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact, written as a short standalone sentence, e.g. 'Ahmed is allergic to shellfish.'"},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "recall",
        "description": "List everything you've remembered about Ahmed in long-term memory. Call this when he asks what you know or remember about him.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "forget",
        "description": "Delete a remembered fact from long-term memory. Call this when Ahmed says to forget something or corrects a fact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "integer", "description": "The fact's number, if known."},
                "text_fragment": {"type": "string", "description": "Part of the fact's text, if the number isn't known."},
            },
        },
    },
    {
        "name": "open_map",
        "description": "Open a location, place, or directions in Google Maps in the browser. Call this whenever the user asks to see a place on a map, find directions, or navigate somewhere.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Place or address to show, e.g. 'Tortilla, Gate Avenue, Dubai'."},
                "directions": {"type": "boolean", "description": "True to open turn-by-turn directions to the place rather than just showing it."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_task",
        "description": "Add a task to the user's to-do list. Call this when the user asks to add, note down, or remember a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The task description."},
                "priority": {"type": "string", "enum": ["low", "normal", "high"], "description": "Task priority (default normal)."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List the user's pending tasks. Call this when the user asks what's on their list or what they need to do.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_done": {"type": "boolean", "description": "Also include completed tasks (default false)."},
            },
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done, by its number or by matching text. Call this when the user says they finished something on their list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task's number, if known."},
                "text_fragment": {"type": "string", "description": "Part of the task's text, if the number isn't known."},
            },
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task from the list entirely (not the same as completing it). Only call this when the user explicitly asks to delete or remove a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task's number."},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "clear_completed_tasks",
        "description": "Remove all completed tasks from the list. Call this when the user asks to clear or clean up completed tasks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "done_today",
        "description": "List tasks the user completed today. Call this when the user asks what they got done today.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Integration tool schemas (only offered when connected) ────

GMAIL_TOOLS = [
    {
        "name": "list_unread_emails",
        "description": "List unread emails in the user's Gmail inbox (sender, subject, snippet). Call this when the user asks about new/unread mail or wants their inbox triaged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "How many to fetch (default 10)."},
            },
        },
    },
    {
        "name": "search_emails",
        "description": "Search Gmail using Gmail's query syntax (e.g. 'from:boss newer_than:7d'). Returns matching messages' sender, subject, date, snippet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query."},
                "max_results": {"type": "integer", "description": "How many to fetch (default 10)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_email",
        "description": "Read the full body of one email by its message id (get the id from list_unread_emails or search_emails first).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The Gmail message id."},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "draft_email",
        "description": "Create a Gmail draft (saved, NOT sent). Use this to prepare a reply for Ahmed to review. No confirmation needed since nothing is sent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject."},
                "body": {"type": "string", "description": "Email body, written in Ahmed's voice."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email immediately from the user's Gmail. This is irreversible; Ahmed is shown a confirmation dialog before it sends. Prefer draft_email unless Ahmed explicitly asks to send.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject."},
                "body": {"type": "string", "description": "Email body."},
            },
            "required": ["to", "subject", "body"],
        },
    },
]

CALENDAR_TOOLS = [
    {
        "name": "list_calendar_events",
        "description": "List the user's Google Calendar events in a time window. Call this when the user asks about their schedule, day, or upcoming events. Provide ISO 8601 timestamps with the Dubai offset (+04:00).",
        "input_schema": {
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "Window start, ISO 8601, e.g. '2026-07-08T00:00:00+04:00'."},
                "time_max": {"type": "string", "description": "Window end, ISO 8601."},
            },
            "required": ["time_min", "time_max"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a Google Calendar event. Ahmed is shown a confirmation dialog before it is created. Use ISO 8601 timestamps with the Dubai offset (+04:00).",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title."},
                "start": {"type": "string", "description": "Start time, ISO 8601."},
                "end": {"type": "string", "description": "End time, ISO 8601."},
                "description": {"type": "string", "description": "Optional details."},
                "location": {"type": "string", "description": "Optional location."},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete a Google Calendar event by its id (get the id from list_calendar_events first). Ahmed is shown a confirmation dialog before deletion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The calendar event id."},
                "summary": {"type": "string", "description": "The event's title, for the confirmation prompt."},
            },
            "required": ["event_id"],
        },
    },
]

DRIVE_TOOLS = [
    {
        "name": "search_drive",
        "description": "Search the user's Google Drive by filename. Returns matching files (id, name, type).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match in the filename."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_drive_file",
        "description": "Read the text content of a Google Drive file by id (get the id from search_drive first). Google Docs are exported to plain text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "The Drive file id."},
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "create_drive_doc",
        "description": "Create a plain-text document in the user's Google Drive. Ahmed is shown a confirmation dialog before it is created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title."},
                "content": {"type": "string", "description": "Document text content."},
            },
            "required": ["title", "content"],
        },
    },
]

NOTION_TOOLS = [
    {
        "name": "search_notion",
        "description": "Search the user's Notion pages and databases shared with the integration. Returns titles, ids, and urls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_notion_page",
        "description": "Read the text of a Notion page by id (get the id from search_notion first).",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "The Notion page id."},
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "create_notion_page",
        "description": "Create a new Notion page under an existing parent page. Ahmed is shown a confirmation dialog before it is created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parent_id": {"type": "string", "description": "Id of an existing page (shared with the integration) to nest under."},
                "title": {"type": "string", "description": "New page title."},
                "content": {"type": "string", "description": "Optional page body text."},
            },
            "required": ["parent_id", "title"],
        },
    },
]


def get_tools() -> list[dict]:
    """Tools offered to Claude this turn: always the local ones, plus any
    integration whose service is actually connected. Keeping unconnected tools
    out of the list stops Claude from calling something that can only fail."""
    tools = list(TOOLS)
    if google.is_available():
        tools += GMAIL_TOOLS + CALENDAR_TOOLS + DRIVE_TOOLS
    if notion.is_available():
        tools += NOTION_TOOLS
    return tools


# ── Dispatcher ────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict) -> str:
    """Run a tool and return a plain-text result. Raises on unknown tool."""

    if name == "get_current_time":
        return get_current_time()

    if name == "get_weather":
        city = tool_input.get("city") or _memory.get("city") or "Dubai"
        w = get_weather(city)
        if not w:
            return f"Weather service unavailable for {city} right now."
        return f"Weather in {city}: {format_weather(w)}"

    if name == "get_news":
        category = tool_input.get("category") or config.NEWS_CATEGORY
        count = tool_input.get("count") or config.NEWS_COUNT
        headlines = get_news(category, count)
        if not headlines:
            return "No headlines available right now."
        return "\n".join(f"• {h}" for h in headlines)

    if name == "get_system_stats":
        return format_system_stats(get_system_stats())

    if name == "web_search":
        results = web_search(tool_input["query"])
        if not results:
            return "No search results found."
        return format_search_results(results)

    if name == "set_reminder":
        message = tool_input["message"]
        minutes = int(tool_input["minutes"])
        set_reminder(message, minutes, _reminder_cb or (lambda text: None))
        return f"Reminder set: '{message}' in {minutes} minute{'s' if minutes != 1 else ''}."

    if name == "open_app":
        return open_app(tool_input["app_name"])

    if name == "delegate":
        # Imported lazily: agents.py imports the brains, which import this module.
        import agents as agent_net
        out = agent_net.dispatch(tool_input["request"], _backend, synthesise=False)
        lines = [f"{r['label']}: {r['output']}" for r in out["results"]]
        return "Specialist reports:\n" + "\n".join(lines)

    if name == "remember":
        import memory_manager
        fact = memory_manager.add_fact(tool_input["fact"])
        _memory.setdefault("facts", [])
        return f"Remembered (#{fact['id']}): {fact['text']}"

    if name == "recall":
        import memory_manager
        facts = memory_manager.list_facts()
        if not facts:
            return "Nothing in long-term memory yet."
        return "\n".join(f"{f['id']}. {f['text']}" for f in facts)

    if name == "forget":
        import memory_manager
        removed = memory_manager.forget_fact(
            fact_id=tool_input.get("fact_id"),
            text_fragment=tool_input.get("text_fragment"),
        )
        if not removed:
            return "No matching fact found in memory."
        return f"Forgotten: {removed['text']}"

    if name == "open_map":
        import webbrowser
        from urllib.parse import quote_plus
        query = tool_input["query"]
        if tool_input.get("directions"):
            url = f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(query)}"
        else:
            url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
        webbrowser.open(url)
        return f"Opened Google Maps for: {query}"

    if name == "add_task":
        priority = tool_input.get("priority", "normal")
        task = task_manager.add_task(tool_input["text"], priority)
        icon = task_manager.PRIORITY_ICONS[priority]
        return f"Added task {task['id']}: {icon} {task['text']}"

    if name == "list_tasks":
        tasks = task_manager.list_tasks(include_done=tool_input.get("include_done", False))
        if not tasks:
            return "The task list is empty — nothing pending."
        return task_manager.format_tasks(tasks, show_done=True)

    if name == "complete_task":
        task_id = tool_input.get("task_id")
        fragment = tool_input.get("text_fragment")
        if not task_id and not fragment:
            return "Need either the task number or part of its text to mark it done."
        task = task_manager.complete_task(task_id=task_id, text_fragment=fragment)
        if not task:
            return "No matching pending task found."
        return f"Marked as done: {task['text']}"

    if name == "delete_task":
        task = task_manager.delete_task(tool_input["task_id"])
        if not task:
            return "No task with that number."
        return f"Deleted task: {task['text']}"

    if name == "clear_completed_tasks":
        count = task_manager.clear_completed()
        return f"Cleared {count} completed task{'s' if count != 1 else ''}."

    if name == "done_today":
        tasks = task_manager.done_today()
        if not tasks:
            return "No tasks completed today yet."
        return task_manager.format_tasks(tasks, show_done=True)

    # ── Gmail ─────────────────────────────────────────────────
    if name == "list_unread_emails":
        limit = tool_input.get("max_results", 10)
        emails = google.list_unread(limit)
        if not emails:
            return "No unread emails."
        # Lead with the true inbox total — the list below is only one page, and
        # without this the model reports the page size as the unread count.
        try:
            total = google.unread_count()
            header = (f"{total} unread emails in total. Showing the {len(emails)} most recent:\n\n"
                      if total > len(emails) else f"{len(emails)} unread emails:\n\n")
        except Exception:
            header = ""
        return header + "\n\n".join(
            f"[{e['id']}] From: {e['sender']}\nSubject: {e['subject']}\n{e['snippet']}"
            for e in emails
        )

    if name == "search_emails":
        emails = google.search_messages(tool_input["query"], tool_input.get("max_results", 10))
        if not emails:
            return "No emails matched that search."
        return "\n\n".join(
            f"[{e['id']}] From: {e['sender']} ({e['date']})\nSubject: {e['subject']}\n{e['snippet']}"
            for e in emails
        )

    if name == "read_email":
        e = google.read_message(tool_input["message_id"])
        return (f"From: {e['sender']}\nDate: {e['date']}\nSubject: {e['subject']}\n\n{e['body']}")

    if name == "draft_email":
        draft_id = google.create_draft(
            tool_input["to"], tool_input["subject"], tool_input["body"])
        return f"Draft saved (id {draft_id}). It's in Gmail's Drafts, not sent."

    if name == "send_email":
        to = tool_input["to"]
        subject = tool_input["subject"]
        _confirm(
            "Send email?",
            f"To: {to}\nSubject: {subject}\n\n{tool_input['body']}",
        )
        sent_id = google.send_email(to, subject, tool_input["body"])
        return f"Sent to {to} (id {sent_id})."

    # ── Calendar ──────────────────────────────────────────────
    if name == "list_calendar_events":
        events = google.list_events(tool_input["time_min"], tool_input["time_max"])
        if not events:
            return "No events in that window."
        return "\n".join(
            f"[{ev['id']}] {ev['start']} — {ev['summary']}"
            + (f" @ {ev['location']}" if ev['location'] else "")
            for ev in events
        )

    if name == "create_calendar_event":
        summary = tool_input["summary"]
        start = tool_input["start"]
        end = tool_input["end"]
        _confirm(
            "Create calendar event?",
            f"{summary}\n{start} → {end}"
            + (f"\n{tool_input.get('location')}" if tool_input.get("location") else ""),
        )
        link = google.create_event(
            summary, start, end,
            tool_input.get("description", ""), tool_input.get("location", ""))
        return f"Event created: {link}"

    if name == "delete_calendar_event":
        label = tool_input.get("summary") or tool_input["event_id"]
        _confirm("Delete calendar event?", f"This will permanently delete: {label}")
        google.delete_event(tool_input["event_id"])
        return f"Deleted event: {label}"

    # ── Drive ─────────────────────────────────────────────────
    if name == "search_drive":
        files = google.search_files(tool_input["query"])
        if not files:
            return "No Drive files matched."
        return "\n".join(f"[{f['id']}] {f['name']} ({f['mimeType']})" for f in files)

    if name == "read_drive_file":
        text = google.read_file(tool_input["file_id"])
        return text[:8000] if text else "(file is empty or unreadable)"

    if name == "create_drive_doc":
        title = tool_input["title"]
        _confirm("Create Drive document?", f"Title: {title}\n\n{tool_input['content'][:500]}")
        link = google.create_doc(title, tool_input["content"])
        return f"Document created: {link}"

    # ── Notion ────────────────────────────────────────────────
    if name == "search_notion":
        results = notion.search(tool_input["query"])
        if not results:
            return "No Notion pages matched."
        return "\n".join(f"[{r['id']}] {r['title']} ({r['type']}) {r['url']}" for r in results)

    if name == "read_notion_page":
        return notion.read_page(tool_input["page_id"])

    if name == "create_notion_page":
        title = tool_input["title"]
        _confirm("Create Notion page?", f"Title: {title}\nUnder parent: {tool_input['parent_id']}")
        url = notion.create_page(
            tool_input["parent_id"], title, tool_input.get("content", ""))
        return f"Notion page created: {url}"

    raise ValueError(f"Unknown tool: {name}")
