import re
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
import threading
import json
import os
from datetime import datetime, date

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    ollama = None
    OLLAMA_AVAILABLE = False   # offline fallback is optional; Claude works without it

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import agent_tools
import claude_client
import config
import memory_manager
import task_manager
from voice_manager import VoiceManager
from tools import (
    detect_command, parse_reminder_text,
    get_system_stats, format_system_stats,
    get_weather, format_weather,
    get_news, open_app, web_search, format_search_results, set_reminder,
    get_current_time,
)
from briefing import build_briefing
import google_integration as google
import scheduler as scheduler_mod

# ── Storage dirs ──────────────────────────────────────────────
_BASE         = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR   = os.path.join(_BASE, "chat_history")
DAILY_LOG_DIR = os.path.join(_BASE, "daily_log")
os.makedirs(HISTORY_DIR,   exist_ok=True)
os.makedirs(DAILY_LOG_DIR, exist_ok=True)

# ── Colours & fonts ───────────────────────────────────────────
BG_COLOR      = "#1e1e2e"
SIDEBAR_COLOR = "#181825"
USER_COLOR    = "#89b4fa"
AI_COLOR      = "#a6e3a1"
INPUT_BG      = "#313244"
TEXT_COLOR    = "#cdd6f4"
BUTTON_COLOR  = "#89b4fa"
MUTED_COLOR   = "#6c7086"
RED_COLOR     = "#f38ba8"
YELLOW_COLOR  = "#f9e2af"
FONT          = ("Helvetica", 13)
FONT_BOLD     = ("Helvetica", 13, "bold")
FONT_SMALL    = ("Helvetica", 11)

# ── App state ─────────────────────────────────────────────────
memory               = memory_manager.load()
messages: list[dict] = []
current_session_file = None
session_files: list[str] = []
_system_panel_visible = True


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def using_claude() -> bool:
    return selected_model.get() == claude_client.CLAUDE_LABEL


def build_messages_with_system() -> list[dict]:
    if using_claude():
        prompt = memory_manager.build_claude_system_prompt(memory)
    else:
        prompt = memory_manager.build_system_prompt(memory)
    return [{"role": "system", "content": prompt}] + messages


def chat_completion(msgs: list[dict]) -> str:
    """Route a chat request to the selected backend: Claude (cloud) or local Ollama."""
    if using_claude():
        system = next((m["content"] for m in msgs if m["role"] == "system"), "")
        convo = [m for m in msgs if m["role"] != "system"]
        return claude_client.call_claude(convo, system=system)
    if not OLLAMA_AVAILABLE:
        raise RuntimeError(
            "Ollama isn't installed. Select 'Claude (cloud)' in the model menu, "
            "or install Ollama for the offline fallback."
        )
    resp = ollama.chat(model=selected_model.get(), messages=msgs)
    return resp["message"]["content"]


# ── Display ───────────────────────────────────────────────────

def show_user_message(text: str):
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END, "You:    ", "user_label")
    chat_display.insert(tk.END, text + "\n\n", "user_text")
    chat_display.config(state=tk.DISABLED)
    chat_display.see(tk.END)


def show_jarvis_message(text: str, speak: bool = True):
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END, "Jarvis: ", "ai_label")
    chat_display.insert(tk.END, text + "\n\n", "ai_text")
    chat_display.config(state=tk.DISABLED)
    chat_display.see(tk.END)
    if speak and voice:
        voice.speak(text)


def show_thinking():
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END, "Jarvis: Thinking…\n", "thinking")
    chat_display.config(state=tk.DISABLED)
    chat_display.see(tk.END)


def remove_thinking():
    chat_display.config(state=tk.NORMAL)
    chat_display.delete("end-2l", "end-1l")
    # leave NORMAL so the caller can insert immediately


def set_status(state: str):
    icons = {
        "ready":     ("🟢", "Ready",       TEXT_COLOR),
        "thinking":  ("🟡", "Thinking…",   YELLOW_COLOR),
        "error":     ("🔴", "Error",        RED_COLOR),
        "listening": ("🎙", "Listening…",  USER_COLOR),
    }
    icon, label, color = icons.get(state, icons["ready"])
    status_label.config(text=f"{icon} {label}", fg=color)


# ── Input re-enable ───────────────────────────────────────────

def _re_enable_input():
    send_button.config(state=tk.NORMAL)
    input_box.config(state=tk.NORMAL)
    input_box.focus()
    set_status("ready")


# ── Toast ─────────────────────────────────────────────────────

def show_toast(message: str, duration: int = 5000):
    toast = tk.Toplevel(window)
    toast.overrideredirect(True)
    toast.configure(bg="#45475a")
    toast.attributes("-topmost", True)
    tk.Label(toast, text=message, bg="#45475a", fg=TEXT_COLOR,
             font=FONT_SMALL, wraplength=300, padx=14, pady=10).pack()
    window.update_idletasks()
    w = toast.winfo_reqwidth()
    h = toast.winfo_reqheight()
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    toast.geometry(f"+{sw - w - 20}+{sh - h - 60}")
    toast.after(duration, toast.destroy)


# ══════════════════════════════════════════════════════════════
# Session management
# ══════════════════════════════════════════════════════════════

def get_session_title() -> str:
    for m in messages:
        if m["role"] == "user":
            t = m["content"][:40]
            return t + ("…" if len(m["content"]) > 40 else "")
    return "New Chat"


def save_current_session():
    global current_session_file
    if not messages:
        return
    if current_session_file is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_session_file = os.path.join(HISTORY_DIR, f"{ts}.json")
    data = {
        "title":     get_session_title(),
        "timestamp": datetime.now().isoformat(),
        "messages":  messages,
    }
    with open(current_session_file, "w") as f:
        json.dump(data, f, indent=2)
    refresh_history_list()


def load_sessions() -> list[tuple[str, str]]:
    out = []
    try:
        for fname in sorted(os.listdir(HISTORY_DIR), reverse=True):
            if fname.endswith(".json"):
                fpath = os.path.join(HISTORY_DIR, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    out.append((fpath, data.get("title", fname)))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def refresh_history_list():
    global session_files
    history_listbox.delete(0, tk.END)
    sessions = load_sessions()
    session_files = [s[0] for s in sessions]
    for _, title in sessions:
        history_listbox.insert(tk.END, title)


def redraw_chat():
    chat_display.config(state=tk.NORMAL)
    chat_display.delete("1.0", tk.END)
    for msg in messages:
        if msg["role"] == "user":
            chat_display.insert(tk.END, "You:    ", "user_label")
            chat_display.insert(tk.END, msg["content"] + "\n\n", "user_text")
        elif msg["role"] == "assistant":
            chat_display.insert(tk.END, "Jarvis: ", "ai_label")
            chat_display.insert(tk.END, msg["content"] + "\n\n", "ai_text")
    chat_display.config(state=tk.DISABLED)
    chat_display.see(tk.END)


def on_session_click(_event):
    global messages, current_session_file
    sel = history_listbox.curselection()
    if not sel:
        return
    fpath = session_files[sel[0]]
    try:
        with open(fpath) as f:
            data = json.load(f)
    except Exception:
        return
    messages = data.get("messages", [])
    current_session_file = fpath
    redraw_chat()


def new_chat():
    global messages, current_session_file
    save_current_session()
    messages = []
    current_session_file = None
    chat_display.config(state=tk.NORMAL)
    chat_display.delete("1.0", tk.END)
    chat_display.config(state=tk.DISABLED)
    show_jarvis_message("A new session has begun. How may I assist you?")
    input_box.focus()


# ══════════════════════════════════════════════════════════════
# Command routing
# ══════════════════════════════════════════════════════════════

def handle_command(cmd: str, user_text: str) -> str | None:
    """Execute a local command. Returns response text, or None if it handled display itself."""

    if cmd == "time":
        return get_current_time()

    if cmd == "system_stats":
        return format_system_stats(get_system_stats())

    if cmd == "weather":
        city = memory.get("city")
        if not city:
            return "I don't know your city yet. Set it in ⚙️ Settings."
        return f"Weather in {city}: {format_weather(get_weather(city))}"

    if cmd == "news":
        headlines = get_news(config.NEWS_CATEGORY, config.NEWS_COUNT)
        if headlines:
            return "Today's headlines:\n" + "\n".join(f"  • {h}" for h in headlines)
        return "No headlines available right now."

    if cmd == "open_app":
        m = re.match(r"^open\s+(.+)", user_text, re.IGNORECASE)
        name = m.group(1).strip() if m else user_text
        return open_app(name)

    if cmd == "reminder":
        msg, mins = parse_reminder_text(user_text)
        if msg and mins:
            def _fire(text):
                window.after(0, lambda: show_toast(text))
                window.after(0, lambda: show_jarvis_message(text))
            set_reminder(msg, mins, _fire)
            return f"Understood. I'll remind you to {msg} in {mins} minute{'s' if mins != 1 else ''}."
        return "Couldn't parse that reminder. Try: 'Remind me to [task] in [N] minutes'."

    if cmd == "web_search":
        query = re.sub(
            r"^(search (for|the web for|online for)?|look up|find out about|research|"
            r"what is the latest on|tell me about)\s+",
            "", user_text, flags=re.IGNORECASE,
        ).strip()
        results = web_search(query)
        if not results:
            return (f"No results found for '{query}'. "
                    f"Add a free TAVILY_API_KEY to your .env for better results.")
        context = format_search_results(results)
        synth_messages = build_messages_with_system() + [{
            "role": "user",
            "content": (
                f"I searched the web for: '{query}'\n\n"
                f"Here are the results:\n{context}\n\n"
                f"Please synthesize these results into a concise, helpful answer."
            ),
        }]
        try:
            return chat_completion(synth_messages)
        except Exception as exc:
            return f"Search succeeded but synthesis failed: {exc}"

    if cmd == "add_task":
        priority = "normal"
        if re.search(r"\b(high|urgent|important)\b", user_text, re.I):
            priority = "high"
        elif re.search(r"\b(low|minor|whenever)\b", user_text, re.I):
            priority = "low"
        task_text = re.sub(
            r"^(add\s+(a\s+)?(high|low|urgent|important|minor|priority\s+)*(priority\s+)?task[:\s]+|"
            r"add to (my )?list[:\s]+|new task[:\s]+)",
            "", user_text, flags=re.I,
        ).strip()
        if not task_text:
            return "What would you like to add? Try: 'Add task call the dentist'."
        task = task_manager.add_task(task_text, priority)
        icon = task_manager.PRIORITY_ICONS[priority]
        return f"Added to your list: {icon} {task['text']}"

    if cmd == "list_tasks":
        tasks = task_manager.list_tasks()
        if not tasks:
            return "Your task list is clear. Nothing pending."
        lines = task_manager.format_tasks(tasks)
        return f"You have {len(tasks)} pending task{'s' if len(tasks) != 1 else ''}:\n{lines}"

    if cmd == "complete_task":
        m = re.search(r"\b(\d+)\b", user_text)
        if m:
            task = task_manager.complete_task(task_id=int(m.group(1)))
        else:
            fragment = re.sub(
                r"\b(mark|complete|finish|done with|completed|task)\b", "",
                user_text, flags=re.I,
            ).strip()
            task = task_manager.complete_task(text_fragment=fragment)
        if task:
            return f"Marked as done: ✅ {task['text']}"
        return "I couldn't find that task. Say 'my tasks' to see your list."

    if cmd == "clear_tasks":
        count = task_manager.clear_completed()
        return (f"Cleared {count} completed task{'s' if count != 1 else ''}."
                if count else "No completed tasks to clear.")

    if cmd == "done_today":
        tasks = task_manager.done_today()
        if not tasks:
            return "No tasks completed today yet."
        lines = task_manager.format_tasks(tasks, show_done=True)
        return f"Completed today ({len(tasks)}):\n{lines}"

    if cmd == "calendar":
        if google.is_available():
            # Calendar lives behind Claude's tools; nudge the user to that mode
            # rather than answering blind in the offline fallback.
            return ("Your Google Calendar is connected. Switch the model to "
                    "'Claude (cloud)' and ask about your schedule — I'll read it live.")
        return ("Google Calendar isn't connected yet. Add your OAuth client-secrets "
                "JSON path to GOOGLE_CALENDAR_CREDENTIALS in .env, then restart me.")

    return None   # unknown command — fall through to AI


# ══════════════════════════════════════════════════════════════
# Send / AI
# ══════════════════════════════════════════════════════════════

def send_message(event=None):
    user_text = input_box.get("1.0", tk.END).strip()
    if not user_text:
        return "break"
    input_box.delete("1.0", tk.END)

    show_user_message(user_text)
    messages.append({"role": "user", "content": user_text})

    send_button.config(state=tk.DISABLED)
    input_box.config(state=tk.DISABLED)

    # Claude decides when to use tools itself — the regex matcher only handles
    # the end-of-day GUI flow there. Ollama (no tool use) keeps the full matcher.
    if using_claude():
        cmd = "end_of_day" if detect_command(user_text) == "end_of_day" else None
    else:
        cmd = detect_command(user_text)

    if cmd == "end_of_day":
        run_end_of_day_summary()
    elif cmd:
        set_status("thinking")
        def _run_cmd():
            result = handle_command(cmd, user_text)
            if result:
                messages.append({"role": "assistant", "content": result})
                window.after(0, lambda: _finish_cmd(result))
            else:
                window.after(0, _re_enable_input)
        threading.Thread(target=_run_cmd, daemon=True).start()
    else:
        set_status("thinking")
        show_thinking()
        threading.Thread(target=_get_ai_response, daemon=True).start()

    return "break"


def _finish_cmd(result: str):
    show_jarvis_message(result)
    save_current_session()
    _re_enable_input()


def _get_ai_response():
    try:
        reply = chat_completion(build_messages_with_system())
        messages.append({"role": "assistant", "content": reply})
        save_current_session()
        window.after(0, _display_ai_response, reply)
    except Exception as exc:
        window.after(0, _display_ai_error, str(exc))


def _display_ai_response(reply: str):
    remove_thinking()
    chat_display.config(state=tk.DISABLED)
    show_jarvis_message(reply)
    set_status("ready")
    _re_enable_input()


def _display_ai_error(error: str):
    remove_thinking()
    chat_display.config(state=tk.DISABLED)
    set_status("error")
    show_jarvis_message(f"I encountered an error: {error}", speak=False)
    _re_enable_input()


# ══════════════════════════════════════════════════════════════
# Morning briefing
# ══════════════════════════════════════════════════════════════

def show_morning_briefing():
    # Stamp the date now so the scheduler treats today's briefing as delivered
    # whether it came from launch or the timer — no double-fire either way.
    memory["last_briefing_date"] = date.today().isoformat()
    memory_manager.save(memory)

    def _build():
        text = build_briefing(memory, config)
        if using_claude() and claude_client.is_configured():
            try:
                text = claude_client.call_claude(
                    [{"role": "user", "content": (
                        "Here is my raw morning briefing data:\n\n" + text +
                        "\n\nRewrite this as a tight, natural morning briefing in your "
                        "voice. Keep every fact; don't invent anything."
                    )}],
                    system=memory_manager.build_claude_system_prompt(memory),
                    use_tools=False,
                )
            except Exception:
                pass  # fall back to the raw concatenated briefing
        window.after(0, lambda: show_jarvis_message(text, speak=True))
    threading.Thread(target=_build, daemon=True).start()


# ══════════════════════════════════════════════════════════════
# End-of-day summary
# ══════════════════════════════════════════════════════════════

def run_end_of_day_summary():
    if not messages:
        _name = memory.get("preferred_name") or memory.get("user_name") or "Ahmed"
        show_jarvis_message(f"Nothing to summarise yet. Goodnight, {_name}.", speak=True)
        _re_enable_input()
        return

    set_status("thinking")
    show_thinking()

    def _generate():
        try:
            summary_msgs = build_messages_with_system() + [{
                "role": "user",
                "content": (
                    "Provide a brief end-of-day summary of our conversation today "
                    "(2-3 sentences). Note main topics, decisions made, and useful "
                    "context for our next session."
                ),
            }]
            summary = chat_completion(summary_msgs)
        except Exception:
            summary = "Unable to generate summary."

        # Save daily log
        today    = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(DAILY_LOG_DIR, f"{today}.md")
        try:
            with open(log_path, "w") as f:
                f.write(f"# Daily Log — {today}\n\n## Summary\n{summary}\n\n## Conversation\n")
                for m in messages:
                    role = "You" if m["role"] == "user" else "Jarvis"
                    f.write(f"\n**{role}:** {m['content']}\n")
        except Exception:
            pass

        memory["last_session_summary"] = summary[:500]
        memory["last_eod_date"] = date.today().isoformat()
        memory_manager.save(memory)

        goodnight = f"{summary}\n\nGoodnight. Today's log has been saved."
        window.after(0, lambda: _show_eod(goodnight))

    threading.Thread(target=_generate, daemon=True).start()


def _show_eod(text: str):
    remove_thinking()
    chat_display.config(state=tk.DISABLED)
    show_jarvis_message(text, speak=True)
    set_status("ready")
    _re_enable_input()


# ══════════════════════════════════════════════════════════════
# Scheduled jobs (auto briefing / EOD / calendar alerts)
# ══════════════════════════════════════════════════════════════

def _scheduled_morning_briefing():
    """Timer-fired morning briefing. show_morning_briefing() stamps the date."""
    show_morning_briefing()


def _scheduled_end_of_day():
    """Timer-fired EOD summary — only bother if there's a conversation to wrap up."""
    if not messages:
        memory["last_eod_date"] = date.today().isoformat()
        memory_manager.save(memory)
        return
    run_end_of_day_summary()


def _calendar_alert(message: str):
    show_toast(message, duration=8000)
    show_jarvis_message(message, speak=True)


# ══════════════════════════════════════════════════════════════
# Proactive flows — inbox triage & draft-in-voice
# ══════════════════════════════════════════════════════════════

def _submit_prompt(text: str):
    """Run a canned instruction through the normal send path so Claude uses its
    real tools (Gmail etc.). Shown as a normal user turn — honest history."""
    input_box.config(state=tk.NORMAL)
    input_box.delete("1.0", tk.END)
    input_box.insert(tk.END, text)
    send_message()


def triage_inbox():
    """Categorize unread mail into URGENT / ACTION / FYI / SKIP via Claude's Gmail tools."""
    if not using_claude():
        show_toast("Inbox triage needs Claude (cloud) mode.")
        return
    _submit_prompt(
        "Triage my unread inbox: pull my unread emails and sort each into one of "
        "URGENT, ACTION, FYI, or SKIP, with a one-line reason. Group by category, "
        "most urgent first."
    )


def draft_in_voice():
    """Ask who/what, then have Jarvis draft an email in Ahmed's voice."""
    to = simpledialog.askstring("Draft email", "Recipient (email address):", parent=window)
    if not to:
        return
    topic = simpledialog.askstring("Draft email", "What should the email say / be about?",
                                   parent=window)
    if not topic:
        return
    if using_claude():
        _submit_prompt(
            f"Draft an email to {to} about: {topic}. Write it in my voice — "
            f"professional but warm, concise. Save it as a Gmail draft using draft_email, "
            f"then show me the text."
        )
    else:
        _submit_prompt(
            f"Draft an email to {to} about: {topic}. Write it in my voice — "
            f"professional but warm, concise. Show me the draft text."
        )


# ══════════════════════════════════════════════════════════════
# Voice callbacks
# ══════════════════════════════════════════════════════════════

def _on_speech_result(text, error):
    if error:
        window.after(0, lambda: set_status("ready"))
        window.after(0, lambda: mic_button.config(text="🎤", bg=INPUT_BG))
        if error != "No speech detected":
            window.after(0, lambda: show_toast(f"Mic: {error}"))
        return
    if text:
        window.after(0, lambda: _inject_speech(text))


def _inject_speech(text: str):
    input_box.config(state=tk.NORMAL)
    input_box.delete("1.0", tk.END)
    input_box.insert(tk.END, text)
    send_message()


def _on_listening_change(is_listening: bool):
    def _update():
        if is_listening:
            mic_button.config(text="⏹", bg=RED_COLOR)
            set_status("listening")
        else:
            mic_button.config(text="🎤", bg=INPUT_BG)
            if status_label.cget("text").startswith("🎙"):
                set_status("ready")
    window.after(0, _update)


def _on_wake_word():
    def _activate():
        show_toast("Wake word detected — listening…")
        if voice:
            _name = memory.get("preferred_name") or memory.get("user_name") or "Ahmed"
            voice.speak(f"Yes, {_name}?")
        toggle_mic()
    window.after(0, _activate)


def toggle_mic():
    if not voice or not voice.mic_available:
        show_toast("No microphone detected")
        return
    if voice.is_listening:
        return
    voice.listen_once()


def toggle_mute():
    muted = voice.toggle_mute() if voice else True
    mute_button.config(text="🔇" if muted else "🔊")


# ══════════════════════════════════════════════════════════════
# System panel
# ══════════════════════════════════════════════════════════════

def toggle_system_panel():
    global _system_panel_visible
    _system_panel_visible = not _system_panel_visible
    if _system_panel_visible:
        system_stats_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
        sys_toggle_btn.config(text="System ▼")
    else:
        system_stats_frame.pack_forget()
        sys_toggle_btn.config(text="System ▶")


def refresh_system_panel():
    if config.ENABLE_SYSTEM_STATS and _system_panel_visible:
        def _fetch():
            stats = get_system_stats()
            window.after(0, lambda: _update_system_labels(stats))
        threading.Thread(target=_fetch, daemon=True).start()
    window.after(5000, refresh_system_panel)


def _update_system_labels(stats: dict):
    if "error" in stats:
        return
    cpu_label.config(text=f"CPU   {stats['cpu_pct']}%")
    ram_label.config(text=f"RAM   {stats['ram_pct']}%")
    if stats["battery"]:
        b = stats["battery"]
        batt_label.config(text=f"Batt  {b['pct']}% {'⚡' if b['charging'] else '🔋'}")
    else:
        batt_label.config(text="Batt  N/A")


# ══════════════════════════════════════════════════════════════
# Settings panel
# ══════════════════════════════════════════════════════════════

def open_settings():
    panel = tk.Toplevel(window)
    panel.title("Settings")
    panel.configure(bg=BG_COLOR)
    panel.geometry("420x520")
    panel.resizable(False, False)
    panel.grab_set()

    def lbl(parent, text, **kw):
        tk.Label(parent, text=text, bg=BG_COLOR, fg=MUTED_COLOR,
                 font=FONT_SMALL, **kw).pack(**{"fill": tk.X, "padx": 20, "pady": (10, 2)})

    def field_row(parent, label, var):
        f = tk.Frame(parent, bg=BG_COLOR)
        f.pack(fill=tk.X, padx=20, pady=2)
        tk.Label(f, text=label, bg=BG_COLOR, fg=TEXT_COLOR,
                 font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
        tk.Entry(f, textvariable=var, bg=INPUT_BG, fg=TEXT_COLOR,
                 font=FONT_SMALL, bd=0, insertbackground=TEXT_COLOR).pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

    tk.Label(panel, text="⚙️  Settings", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_BOLD).pack(pady=(18, 4))

    lbl(panel, "— Identity —")
    name_var = tk.StringVar(value=memory.get("user_name") or "")
    city_var = tk.StringVar(value=memory.get("city") or "")
    field_row(panel, "Your name", name_var)
    field_row(panel, "City", city_var)

    lbl(panel, "— Voice —")

    voice_var = tk.BooleanVar(value=config.ENABLE_VOICE)
    f = tk.Frame(panel, bg=BG_COLOR); f.pack(fill=tk.X, padx=20, pady=2)
    tk.Label(f, text="Voice enabled", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
    tk.Checkbutton(f, variable=voice_var, bg=BG_COLOR, fg=TEXT_COLOR,
                   selectcolor=INPUT_BG, activebackground=BG_COLOR).pack(side=tk.LEFT)

    gender_var = tk.StringVar(value=config.VOICE_GENDER)
    f = tk.Frame(panel, bg=BG_COLOR); f.pack(fill=tk.X, padx=20, pady=2)
    tk.Label(f, text="Voice gender", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
    for val, lbl_text in [("male", "Male"), ("female", "Female")]:
        tk.Radiobutton(f, text=lbl_text, variable=gender_var, value=val,
                       bg=BG_COLOR, fg=TEXT_COLOR, selectcolor=INPUT_BG,
                       activebackground=BG_COLOR).pack(side=tk.LEFT, padx=4)

    speed_var = tk.IntVar(value=config.VOICE_SPEED)
    f = tk.Frame(panel, bg=BG_COLOR); f.pack(fill=tk.X, padx=20, pady=2)
    tk.Label(f, text="Speed (wpm)", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
    tk.Scale(f, variable=speed_var, from_=100, to=280, orient=tk.HORIZONTAL,
             bg=BG_COLOR, fg=TEXT_COLOR, troughcolor=INPUT_BG,
             highlightthickness=0).pack(side=tk.LEFT, fill=tk.X, expand=True)

    wake_var = tk.BooleanVar(value=config.ENABLE_WAKE_WORD)
    f = tk.Frame(panel, bg=BG_COLOR); f.pack(fill=tk.X, padx=20, pady=2)
    tk.Label(f, text="Wake word", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
    tk.Checkbutton(f, variable=wake_var, bg=BG_COLOR, fg=TEXT_COLOR,
                   selectcolor=INPUT_BG, activebackground=BG_COLOR).pack(side=tk.LEFT)

    lbl(panel, "— News —")
    news_var = tk.StringVar(value=config.NEWS_CATEGORY)
    f = tk.Frame(panel, bg=BG_COLOR); f.pack(fill=tk.X, padx=20, pady=2)
    tk.Label(f, text="Category", bg=BG_COLOR, fg=TEXT_COLOR,
             font=FONT_SMALL, width=14, anchor="w").pack(side=tk.LEFT)
    cats = ["general", "technology", "science", "health", "business", "sports"]
    om = tk.OptionMenu(f, news_var, *cats)
    om.config(bg=INPUT_BG, fg=TEXT_COLOR, font=FONT_SMALL,
              highlightthickness=0, bd=0, activebackground="#45475a")
    om["menu"].config(bg=INPUT_BG, fg=TEXT_COLOR, font=FONT_SMALL)
    om.pack(side=tk.LEFT)

    def _save():
        memory["user_name"]      = name_var.get().strip() or None
        memory["preferred_name"] = name_var.get().strip() or None
        memory["city"]           = city_var.get().strip() or None
        memory_manager.save(memory)
        config.ENABLE_VOICE      = voice_var.get()
        config.VOICE_GENDER      = gender_var.get()
        config.VOICE_SPEED       = speed_var.get()
        config.ENABLE_WAKE_WORD  = wake_var.get()
        config.NEWS_CATEGORY     = news_var.get()
        if voice:
            voice.update_voice_settings()
        panel.destroy()
        show_toast("Settings saved.")

    tk.Button(panel, text="Save", font=FONT_BOLD,
              bg=BUTTON_COLOR, fg=BG_COLOR, bd=0,
              padx=24, pady=8, cursor="hand2",
              command=_save).pack(pady=20)


# ══════════════════════════════════════════════════════════════
# Onboarding
# ══════════════════════════════════════════════════════════════

def maybe_run_onboarding():
    if not memory.get("first_launch", True):
        window.after(400, show_morning_briefing)
        return

    def _step1():
        show_jarvis_message(
            "Hello. I am Jarvis — your personal AI assistant. "
            "Before we begin, I have two quick questions.",
            speak=True,
        )
        window.after(1200, _step2)

    def _step2():
        name = simpledialog.askstring("Setup", "What is your name?", parent=window)
        if name:
            memory["user_name"]      = name.strip()
            memory["preferred_name"] = name.strip()
        window.after(100, _step3)

    def _step3():
        city = simpledialog.askstring(
            "Setup", "What city are you in? (used for weather updates)", parent=window
        )
        if city:
            memory["city"] = city.strip()
        memory["first_launch"] = False
        memory_manager.save(memory)
        show_jarvis_message(
            f"Excellent. Good to meet you, "
            f"{memory.get('preferred_name') or 'Ahmed'}. Let me prepare your briefing.",
            speak=True,
        )
        window.after(600, show_morning_briefing)

    window.after(300, _step1)


# ── Close ─────────────────────────────────────────────────────

def on_close():
    save_current_session()
    try:
        job_scheduler.stop()
    except Exception:
        pass
    if voice:
        voice.stop_wake_word_listener()
    window.destroy()


# ══════════════════════════════════════════════════════════════
# Build the window
# ══════════════════════════════════════════════════════════════

window = tk.Tk()
window.title("Jarvis")
window.geometry("980x660")
window.configure(bg=BG_COLOR)
window.resizable(True, True)
window.minsize(720, 460)
window.protocol("WM_DELETE_WINDOW", on_close)

# ── Voice init ────────────────────────────────────────────────
voice: VoiceManager | None = None
try:
    voice = VoiceManager(config)
    voice.on_speech_result    = _on_speech_result
    voice.on_listening_change = _on_listening_change
    voice.on_wake_word        = _on_wake_word
except Exception:
    voice = None

# ── Sidebar ───────────────────────────────────────────────────
sidebar = tk.Frame(window, bg=SIDEBAR_COLOR, width=220)
sidebar.pack(side=tk.LEFT, fill=tk.Y)
sidebar.pack_propagate(False)

tk.Label(sidebar, text="JARVIS", bg=SIDEBAR_COLOR, fg=USER_COLOR,
         font=("Helvetica", 14, "bold"), anchor="w").pack(fill=tk.X, padx=14, pady=(14, 8))

tk.Button(sidebar, text="+ New Chat", font=FONT_SMALL,
          bg=BUTTON_COLOR, fg=BG_COLOR, bd=0,
          padx=10, pady=6, cursor="hand2",
          command=new_chat).pack(fill=tk.X, padx=10, pady=(0, 8))

tk.Label(sidebar, text="History", bg=SIDEBAR_COLOR, fg=MUTED_COLOR,
         font=("Helvetica", 10, "bold"), anchor="w").pack(fill=tk.X, padx=14, pady=(4, 2))

list_frame = tk.Frame(sidebar, bg=SIDEBAR_COLOR)
list_frame.pack(fill=tk.BOTH, expand=True, padx=6)

hist_scroll = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
history_listbox = tk.Listbox(
    list_frame, yscrollcommand=hist_scroll.set,
    bg=SIDEBAR_COLOR, fg=TEXT_COLOR, font=FONT_SMALL,
    bd=0, highlightthickness=0, selectbackground="#45475a",
    activestyle="none", cursor="hand2",
)
hist_scroll.config(command=history_listbox.yview)
hist_scroll.pack(side=tk.RIGHT, fill=tk.Y)
history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
history_listbox.bind("<<ListboxSelect>>", on_session_click)

# Separator
tk.Frame(sidebar, bg="#313244", height=1).pack(fill=tk.X, padx=8, pady=6)

# System panel toggle
sys_toggle_btn = tk.Button(
    sidebar, text="System ▼", font=("Helvetica", 10, "bold"),
    bg=SIDEBAR_COLOR, fg=MUTED_COLOR, bd=0,
    activebackground=SIDEBAR_COLOR, activeforeground=MUTED_COLOR,
    anchor="w", cursor="hand2", command=toggle_system_panel,
)
sys_toggle_btn.pack(fill=tk.X, padx=10, pady=(0, 2))

system_stats_frame = tk.Frame(sidebar, bg=SIDEBAR_COLOR)
system_stats_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

cpu_label  = tk.Label(system_stats_frame, text="CPU   —", bg=SIDEBAR_COLOR,
                       fg=TEXT_COLOR, font=FONT_SMALL, anchor="w")
cpu_label.pack(fill=tk.X, padx=6, pady=1)
ram_label  = tk.Label(system_stats_frame, text="RAM   —", bg=SIDEBAR_COLOR,
                       fg=TEXT_COLOR, font=FONT_SMALL, anchor="w")
ram_label.pack(fill=tk.X, padx=6, pady=1)
batt_label = tk.Label(system_stats_frame, text="Batt  —", bg=SIDEBAR_COLOR,
                       fg=TEXT_COLOR, font=FONT_SMALL, anchor="w")
batt_label.pack(fill=tk.X, padx=6, pady=1)

# ── Main area ─────────────────────────────────────────────────
main_frame = tk.Frame(window, bg=BG_COLOR)
main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Header
header_frame = tk.Frame(main_frame, bg=BG_COLOR)
header_frame.pack(fill=tk.X, padx=15, pady=(12, 4))

tk.Label(header_frame, text="🤖 Jarvis", bg=BG_COLOR, fg=TEXT_COLOR,
         font=("Helvetica", 15, "bold")).pack(side=tk.LEFT)

status_label = tk.Label(header_frame, text="🟢 Ready", bg=BG_COLOR,
                         fg=TEXT_COLOR, font=FONT_SMALL)
status_label.pack(side=tk.LEFT, padx=(14, 0))

# Right controls (pack right-to-left)
settings_btn = tk.Button(header_frame, text="⚙️", font=FONT,
                          bg=BG_COLOR, fg=TEXT_COLOR, bd=0,
                          activebackground=BG_COLOR, cursor="hand2",
                          command=open_settings)
settings_btn.pack(side=tk.RIGHT, padx=(4, 0))

mute_button = tk.Button(header_frame, text="🔊", font=FONT,
                         bg=BG_COLOR, fg=TEXT_COLOR, bd=0,
                         activebackground=BG_COLOR, cursor="hand2",
                         command=toggle_mute)
mute_button.pack(side=tk.RIGHT, padx=(4, 0))

draft_btn = tk.Button(header_frame, text="✍️", font=FONT,
                      bg=BG_COLOR, fg=TEXT_COLOR, bd=0,
                      activebackground=BG_COLOR, cursor="hand2",
                      command=draft_in_voice)
draft_btn.pack(side=tk.RIGHT, padx=(4, 0))

triage_btn = tk.Button(header_frame, text="📥", font=FONT,
                       bg=BG_COLOR, fg=TEXT_COLOR, bd=0,
                       activebackground=BG_COLOR, cursor="hand2",
                       command=triage_inbox)
triage_btn.pack(side=tk.RIGHT, padx=(4, 0))

# Model selector
available_models: list[str] = []
if OLLAMA_AVAILABLE:
    try:
        result = ollama.list()
        raw = result.models if hasattr(result, "models") else result.get("models", [])
        for m in raw:
            name = m.model if hasattr(m, "model") else (m.get("name") or m.get("model"))
            if name:
                available_models.append(name)
    except Exception:
        pass
    if not available_models:
        available_models = [config.DEFAULT_MODEL]

available_models.append(claude_client.CLAUDE_LABEL)

# Prefer Claude when a key is configured; otherwise first local model
_default = claude_client.CLAUDE_LABEL if claude_client.is_configured() else available_models[0]
selected_model = tk.StringVar(value=_default)

tk.Label(header_frame, text="Model:", bg=BG_COLOR, fg=MUTED_COLOR,
         font=FONT_SMALL).pack(side=tk.RIGHT, padx=(0, 4))
model_menu = tk.OptionMenu(header_frame, selected_model, *available_models)
model_menu.config(bg=INPUT_BG, fg=TEXT_COLOR, font=FONT_SMALL,
                  activebackground="#45475a", activeforeground=TEXT_COLOR,
                  highlightthickness=0, bd=0, cursor="hand2")
model_menu["menu"].config(bg=INPUT_BG, fg=TEXT_COLOR, font=FONT_SMALL,
                          activebackground="#45475a", activeforeground=TEXT_COLOR)
model_menu.pack(side=tk.RIGHT, padx=(0, 10))

# Chat display
chat_display = scrolledtext.ScrolledText(
    main_frame, wrap=tk.WORD, state=tk.DISABLED,
    bg=BG_COLOR, fg=TEXT_COLOR, font=FONT,
    bd=0, padx=10, pady=10, insertbackground=TEXT_COLOR,
)
chat_display.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

chat_display.tag_config("user_label", foreground=USER_COLOR, font=FONT_BOLD)
chat_display.tag_config("user_text",  foreground=TEXT_COLOR, font=FONT)
chat_display.tag_config("ai_label",   foreground=AI_COLOR,   font=FONT_BOLD)
chat_display.tag_config("ai_text",    foreground=TEXT_COLOR, font=FONT)
chat_display.tag_config("thinking",   foreground=MUTED_COLOR, font=FONT)

# Bottom bar
bottom_frame = tk.Frame(main_frame, bg=BG_COLOR)
bottom_frame.pack(padx=15, pady=(0, 8), fill=tk.X)

input_box = tk.Text(bottom_frame, height=2, font=FONT,
                    bg=INPUT_BG, fg=TEXT_COLOR, bd=0,
                    padx=10, pady=8, insertbackground=TEXT_COLOR,
                    wrap=tk.WORD)
input_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
input_box.bind("<Return>", send_message)
input_box.bind("<Shift-Return>", lambda e: None)
input_box.focus()

mic_button = tk.Button(bottom_frame, text="🎤", font=FONT,
                        bg=INPUT_BG, fg=TEXT_COLOR, bd=0,
                        padx=8, pady=8, cursor="hand2",
                        command=toggle_mic)
mic_button.pack(side=tk.LEFT, padx=(0, 6))

send_button = tk.Button(bottom_frame, text="Send", font=FONT_BOLD,
                         bg=BUTTON_COLOR, fg=BG_COLOR, bd=0,
                         padx=20, pady=8, cursor="hand2",
                         command=send_message)
send_button.pack(side=tk.RIGHT)

tk.Label(main_frame,
         text="Enter to send  •  Shift+Enter for new line  •  🎤 mic to speak",
         bg=BG_COLOR, fg=MUTED_COLOR, font=("Helvetica", 10)).pack(pady=(0, 8))

# ── Initialise ────────────────────────────────────────────────

def _reminder_fire(text: str):
    window.after(0, lambda: show_toast(text))
    window.after(0, lambda: show_jarvis_message(text))


def _confirm_action(title: str, detail: str) -> bool:
    """Show a modal Yes/No dialog before a side-effectful tool runs.

    execute_tool() runs on a worker thread, but Tkinter is single-threaded, so
    marshal the dialog onto the main thread and block the worker until Ahmed
    answers. Returns True only on an explicit Yes.
    """
    if threading.current_thread() is threading.main_thread():
        return bool(messagebox.askyesno(title, detail, parent=window))

    done = threading.Event()
    answer = {"ok": False}

    def _ask():
        try:
            answer["ok"] = bool(messagebox.askyesno(title, detail, parent=window))
        finally:
            done.set()

    window.after(0, _ask)
    done.wait()
    return answer["ok"]


agent_tools.set_context(memory, reminder_callback=_reminder_fire,
                        confirm_callback=_confirm_action)

# Daily scheduler: auto morning briefing, EOD summary, and calendar alerts.
job_scheduler = scheduler_mod.Scheduler(
    window, config, memory,
    on_morning_briefing=_scheduled_morning_briefing,
    on_end_of_day=_scheduled_end_of_day,
    on_calendar_alert=_calendar_alert,
    get_upcoming_events=lambda mins: scheduler_mod.upcoming_events_within(google, mins),
)

refresh_history_list()
window.after(500,  refresh_system_panel)
window.after(300,  maybe_run_onboarding)
window.after(2000, job_scheduler.start)
if voice:
    window.after(1500, voice.start_wake_word_listener)

# ── Run ───────────────────────────────────────────────────────
window.mainloop()
