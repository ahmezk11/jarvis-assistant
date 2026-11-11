#!/bin/bash
# Launcher for EDITH's web HUD server.
#
# Used both for manual runs and by the launchd service. Rebuilds the front-end
# only when it's missing, then execs uvicorn so launchd supervises the real
# process (rather than a wrapper shell) and can restart it cleanly.

cd "$(dirname "$0")" || exit 1

# Prevents a native SIGABRT on macOS when Google's client library forks after
# the Objective-C runtime has initialised.
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export NO_PROXY='*'

# Build the SPA if it hasn't been built yet (npm must be on PATH).
if [ ! -d web/frontend/dist ] && command -v npm >/dev/null 2>&1; then
  echo "[edith] building front-end…"
  (cd web/frontend && npm install --silent && npm run build)
fi

PORT="${EDITH_PORT:-8000}"
echo "[edith] starting on http://localhost:$PORT"
exec python3 -m uvicorn web.api:app --host 127.0.0.1 --port "$PORT" --log-level info
