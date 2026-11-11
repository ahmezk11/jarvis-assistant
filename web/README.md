# EDITH — Web HUD

An Iron Man-style browser command centre for EDITH: an arc-reactor
core, a live chat channel wired to the Claude brain and all 27 tools, and live
panels for weather, system, calendar, inbox and tasks.

It does **not** replace the Python backend — it wraps it. A thin FastAPI bridge
(`api.py`) exposes the existing modules (`claude_client`, `agent_tools`,
`task_manager`, `google_integration`, `notion_integration`, `briefing`, …) over
local HTTP; the React front-end in `frontend/` renders the HUD.

```
web/
  api.py              FastAPI bridge → the existing assistant modules
  frontend/           Vite + React + TypeScript + Tailwind v4 + Framer Motion
    src/
      App.tsx         Layout: status bar · chat · reactor core · data panels
      api.ts          Typed client for /api/*
      components/     ArcReactorCore, StatusBar, ChatPanel, ConfirmModal, panels/…
```

## Design language

Grounded in the real Iron Man HUD: near-black blue voids, electric **cyan**
(`#38e1ff`) as the system colour, Stark **gold** and alert **red** accents,
technical condensed type (Orbitron / Rajdhani / Share Tech Mono), everything
edge-lit and animated — concentric rotating rings, a pulsing glass core, corner
brackets, scan lines, and an intel-feed ticker. The reactor shifts colour and
energy with EDITH's state (idle / listening / thinking / responding).

Voice uses the browser: **Web Speech API** for the mic, `speechSynthesis` for
replies. A **"Hey Edith" wake word** (`useWakeWord.ts`) runs a continuous
recogniser in the background — say *"Hey Edith, <command>"* or just *"Hey Edith"*
then your command; a two-tone chime acknowledges. It pauses itself while EDITH is
speaking or thinking so it never hears its own voice, and there's a toggle in the
status bar. The boot overlay exists because browsers block audio + mic until a
user gesture — clicking it unlocks both and speaks the briefing.

Side-effect tools (send mail, calendar/Drive/Notion writes) stay
confirmation-gated — an EDITH authorisation modal, fail-closed on timeout.

## Run it

Fastest path (serves the pre-built front-end and the API on one port):

```bash
cd ~/Desktop/coding\ projects/my-ai-chatbot
pip3 install -r requirements.txt          # once — installs fastapi + uvicorn
python3 -m uvicorn web.api:app --port 8000 # then open http://localhost:8000
```

### Developing the front-end (hot reload)

Run the API and the Vite dev server side by side — Vite proxies `/api` to :8000:

```bash
# terminal 1 — API
python3 -m uvicorn web.api:app --port 8000
# terminal 2 — front-end with HMR at http://localhost:5173
cd web/frontend && npm install && npm run dev
```

After front-end changes, rebuild the static bundle so the single-port command
serves the latest:

```bash
cd web/frontend && npm run build     # outputs web/frontend/dist/
```

`api.py` auto-serves `frontend/dist/` at `/` when it exists.
