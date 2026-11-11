import json
import os
from datetime import datetime

TASKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")

PRIORITY_ICONS = {"high": "🔴", "normal": "⚪", "low": "🔵"}


# ── Internal helpers ──────────────────────────────────────────

def _load() -> list:
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save(tasks: list):
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def _next_id(tasks: list) -> int:
    return max((t["id"] for t in tasks), default=0) + 1


# ── Public API ────────────────────────────────────────────────

def add_task(text: str, priority: str = "normal") -> dict:
    tasks = _load()
    task = {
        "id":       _next_id(tasks),
        "text":     text,
        "priority": priority,   # "low" | "normal" | "high"
        "done":     False,
        "created":  datetime.now().isoformat(),
        "done_at":  None,
    }
    tasks.append(task)
    _save(tasks)
    return task


def list_tasks(include_done: bool = False) -> list:
    tasks = _load()
    if not include_done:
        return [t for t in tasks if not t["done"]]
    return tasks


def complete_task(task_id: int = None, text_fragment: str = None) -> dict | None:
    tasks = _load()
    for t in tasks:
        if t["done"]:
            continue
        match = (task_id and t["id"] == task_id) or \
                (text_fragment and text_fragment.lower() in t["text"].lower())
        if match:
            t["done"]    = True
            t["done_at"] = datetime.now().isoformat()
            _save(tasks)
            return t
    return None


def delete_task(task_id: int) -> dict | None:
    tasks = _load()
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            removed = tasks.pop(i)
            _save(tasks)
            return removed
    return None


def clear_completed() -> int:
    tasks  = _load()
    before = len(tasks)
    tasks  = [t for t in tasks if not t["done"]]
    _save(tasks)
    return before - len(tasks)


def done_today() -> list:
    tasks = _load()
    today = datetime.now().date().isoformat()
    return [t for t in tasks if t["done"] and (t.get("done_at") or "").startswith(today)]


# ── Formatting ────────────────────────────────────────────────

def format_tasks(tasks: list, show_done: bool = False) -> str:
    if not tasks:
        return "  (none)"
    lines = []
    for t in tasks:
        icon = "✅" if t["done"] else PRIORITY_ICONS.get(t.get("priority", "normal"), "⚪")
        lines.append(f"  {t['id']}. {icon} {t['text']}")
    return "\n".join(lines)
