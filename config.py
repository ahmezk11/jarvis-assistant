# ── Feature Flags ─────────────────────────────────────────────
# Set to False to silently disable that feature

ENABLE_VOICE            = True    # TTS output
ENABLE_WAKE_WORD        = True    # "Hey Edith" background listener
ENABLE_CALENDAR         = False   # Google Calendar — requires OAuth setup
ENABLE_NOTION           = False   # Notion — requires API key
ENABLE_NEWS             = True    # Top headlines (BBC RSS or NewsAPI)
ENABLE_WEATHER          = True    # Weather via wttr.in (no key needed)
ENABLE_SYSTEM_STATS     = True    # CPU / RAM / battery via psutil
ENABLE_PROACTIVE_ALERTS = True    # Calendar alerts before events (auto-idle if Google not connected)

# ── Voice ─────────────────────────────────────────────────────
VOICE_SPEED  = 175       # words per minute (pyttsx3)
VOICE_GENDER = "female"  # "male" or "female"

# ── Wake Word ─────────────────────────────────────────────────
WAKE_WORD                  = "hey edith"
WAKE_WORD_ENERGY_THRESHOLD = 4000   # mic sensitivity; raise if too many false positives

# ── Alerts ────────────────────────────────────────────────────
ALERT_CHECK_INTERVAL   = 60    # seconds between proactive-alert sweeps
CALENDAR_ALERT_MINUTES = 10    # alert this many minutes before a calendar event

# ── Scheduled jobs ────────────────────────────────────────────
# Automatic morning briefing and end-of-day summary on a daily timer, plus
# proactive calendar alerts. All fire through the GUI event loop; each runs at
# most once per calendar day. Turn any of them off here.
ENABLE_SCHEDULED_JOBS  = True    # master switch for the daily scheduler
AUTO_MORNING_BRIEFING  = True    # fire the briefing once a day at MORNING_BRIEFING_TIME
AUTO_END_OF_DAY        = True    # fire the EOD summary once a day at END_OF_DAY_TIME
MORNING_BRIEFING_TIME  = "08:00" # HH:MM, 24h local (Asia/Dubai)
END_OF_DAY_TIME        = "22:00" # HH:MM, 24h local (Asia/Dubai)
SCHEDULER_TICK_SECONDS = 60      # how often the scheduler checks the clock

# ── News ──────────────────────────────────────────────────────
NEWS_CATEGORY = "general"   # general | technology | science | health | business | sports
NEWS_COUNT    = 3

# ── Ollama ────────────────────────────────────────────────────
DEFAULT_MODEL = "llama3.2"

# ── App identity ──────────────────────────────────────────────
APP_NAME   = "EDITH"
USER_TITLE = "Ahmed"   # how EDITH addresses you until your name is set
