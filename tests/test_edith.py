"""Tests for EDITH's core logic.

Deliberately focused on the paths that have already produced real bugs:
scheduler double-firing, agent routing, memory persistence, speech cleaning,
and the tool dispatcher. Everything here runs offline — no API keys, no
network, no Ollama — so the suite is fast and always runnable.
"""

import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agents  # noqa: E402
import config  # noqa: E402
import memory_manager  # noqa: E402
import scheduler  # noqa: E402
import task_manager  # noqa: E402


# ── Scheduler ─────────────────────────────────────────────────────────────

def _sched(memory, **cbs):
    defaults = dict(on_morning_briefing=lambda: None, on_end_of_day=lambda: None,
                    on_calendar_alert=lambda m: None, get_upcoming_events=lambda m: [])
    defaults.update(cbs)
    return scheduler.BackgroundScheduler(config, memory, **defaults)


def test_briefing_and_eod_fire_once_per_day():
    """Regression: ticking every minute must not re-fire the daily jobs."""
    mem = {"last_briefing_date": None, "last_eod_date": None}
    fired = []

    def brief():
        fired.append("briefing")
        mem["last_briefing_date"] = date.today().isoformat()

    def eod():
        fired.append("eod")
        mem["last_eod_date"] = date.today().isoformat()

    s = _sched(mem, on_morning_briefing=brief, on_end_of_day=eod)
    for hour, minute in [(9, 0), (9, 1), (12, 0), (22, 30), (22, 31), (23, 0)]:
        s._check(datetime.now().replace(hour=hour, minute=minute))

    assert fired.count("briefing") == 1
    assert fired.count("eod") == 1


def test_jobs_do_not_fire_before_their_time():
    mem = {"last_briefing_date": None, "last_eod_date": None}
    fired = []
    s = _sched(mem, on_morning_briefing=lambda: fired.append("briefing"),
               on_end_of_day=lambda: fired.append("eod"))
    s._check(datetime.now().replace(hour=6, minute=0))  # before 08:00 and 22:00
    assert fired == []


def test_calendar_alert_fires_once_per_event():
    mem = {"last_briefing_date": date.today().isoformat(),
           "last_eod_date": date.today().isoformat()}
    alerts = []
    s = _sched(mem, on_calendar_alert=alerts.append,
               get_upcoming_events=lambda m: [
                   {"id": "evt1", "summary": "Standup", "minutes_until": 5}])
    now = datetime.now().replace(hour=9, minute=0)
    s._check(now)
    s._check(now)  # same event, second tick
    assert len(alerts) == 1
    assert "Standup" in alerts[0]


@pytest.mark.parametrize("value,expected", [
    ("08:00", (8, 0)), ("22:30", (22, 30)),
    ("junk", (0, 0)), ("99:99", (0, 0)),
])
def test_parse_hhmm(value, expected):
    assert scheduler._parse_hhmm(value) == expected


# ── Agent network ─────────────────────────────────────────────────────────

def test_every_agent_has_a_narrow_valid_toolset():
    """Narrow slices are the whole point — and every tool must really exist."""
    import agent_tools
    real = {t["name"] for t in agent_tools.TOOLS}
    for group in (agent_tools.GMAIL_TOOLS, agent_tools.CALENDAR_TOOLS,
                  agent_tools.DRIVE_TOOLS, agent_tools.NOTION_TOOLS):
        real |= {t["name"] for t in group}

    for agent_id, spec in agents.AGENTS.items():
        assert spec["tools"], f"{agent_id} has no tools"
        assert len(spec["tools"]) <= 10, f"{agent_id} slice is too wide"
        for tool in spec["tools"]:
            assert tool in real, f"{agent_id} references unknown tool {tool}"


@pytest.mark.parametrize("request_text,expected", [
    ("do I have any unread email?", "inbox"),
    ("what's on my calendar today?", "scheduler"),
    ("add milk to my task list", "taskmaster"),
    ("what's the weather?", "operator"),
    ("search for the latest news", "researcher"),
])
def test_fallback_router_picks_the_right_specialist(request_text, expected):
    """The keyword fallback runs whenever the model's JSON plan won't parse,
    so it has to be right on its own."""
    plan = agents._fallback_plan(request_text)
    assert expected in [step["agent"] for step in plan]


def test_fallback_router_always_returns_a_plan():
    plan = agents._fallback_plan("something totally unrecognisable zxqv")
    assert len(plan) >= 1
    assert all(step["agent"] in agents.AGENTS for step in plan)


def test_activity_states_reset():
    agents.reset_activity()
    assert set(agents.activity().values()) == {"idle"}


# ── Long-term memory ──────────────────────────────────────────────────────

def test_memory_facts_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_manager, "MEMORY_FILE", str(tmp_path / "memory.json"))

    fact = memory_manager.add_fact("Ahmed is based in Dubai.")
    assert fact["id"] == 1
    assert memory_manager.add_fact("Ahmed is based in Dubai.")["id"] == 1, "duplicate"

    memory_manager.add_fact("Ahmed prefers concise answers.")
    assert len(memory_manager.list_facts()) == 2

    assert memory_manager.forget_fact(text_fragment="Dubai") is not None
    assert len(memory_manager.list_facts()) == 1
    assert memory_manager.forget_fact(fact_id=999) is None


def test_facts_reach_the_system_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_manager, "MEMORY_FILE", str(tmp_path / "memory.json"))
    memory_manager.add_fact("Ahmed is allergic to shellfish.")
    prompt = memory_manager.build_claude_system_prompt(memory_manager.load())
    assert "shellfish" in prompt


def test_system_prompt_has_current_date_and_identity():
    """Regression: without the date EDITH claimed a live World Cup hadn't started."""
    prompt = memory_manager.build_claude_system_prompt(memory_manager.load())
    assert "EDITH" in prompt
    assert str(datetime.now().year) in prompt
    assert "web_search" in prompt, "must be steered to search for live facts"


# ── Tasks ─────────────────────────────────────────────────────────────────

def test_task_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(task_manager, "TASKS_FILE", str(tmp_path / "tasks.json"))

    t = task_manager.add_task("Write tests", "high")
    assert t["priority"] == "high" and not t["done"]
    assert len(task_manager.list_tasks()) == 1

    assert task_manager.complete_task(task_id=t["id"])["done"] is True
    assert task_manager.list_tasks() == []           # pending only
    assert len(task_manager.list_tasks(include_done=True)) == 1
    assert len(task_manager.done_today()) == 1
    assert task_manager.clear_completed() == 1


# ── Speech cleaning (mirrors the front-end rules) ──────────────────────────

def test_speech_text_should_not_contain_markdown_or_emoji():
    """The local model leaked '**bold**' and emoji into spoken output."""
    import re

    def clean(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"[\U0001F000-\U0001FAFF]", " ", text)
        return re.sub(r"[*_`#]", " ", text).strip()

    out = clean("**Tortilla** is great 🌮 and #1")
    assert "**" not in out and "🌮" not in out and "#" not in out
    assert "Tortilla" in out
