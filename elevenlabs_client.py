"""ElevenLabs text-to-speech for EDITH.

Gives EDITH a real, natural voice instead of the browser's built-in speech
synthesis. Everything degrades gracefully: no API key, no quota, or any network
failure simply returns None and the front-end falls back to the browser voice —
EDITH never goes silent.

Credits are the scarce resource on the free tier (~10k characters/month), so
audio is cached on disk by (text, voice, model). The morning briefing is
near-identical each day, and the boot greeting is identical every launch, so the
cache saves a large share of real usage.
"""

import hashlib
import os
import threading

import requests

API_BASE = "https://api.elevenlabs.io/v1"

# The voice Ahmed picked from the ElevenLabs voice library.
DEFAULT_VOICE_ID = "jv41DhCf464zw0TI7I1w"

# flash_v2_5 costs half the credits of the standard models and is the lowest
# latency, which matters for a voice assistant. Override with ELEVENLABS_MODEL.
DEFAULT_MODEL = "eleven_flash_v2_5"

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tts_cache")
_cache_lock = threading.Lock()

# Set when the API reports the quota is gone, so we stop hammering a dead
# endpoint and fall back to the browser voice for the rest of the session.
_quota_exhausted = False


def _api_key() -> str | None:
    return os.getenv("ELEVENLABS_API_KEY") or None


def voice_id() -> str:
    return os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID


def model_id() -> str:
    return os.getenv("ELEVENLABS_MODEL") or DEFAULT_MODEL


def is_configured() -> bool:
    return bool(_api_key()) and not _quota_exhausted


def status() -> dict:
    return {
        "configured": bool(_api_key()),
        "available": is_configured(),
        "quota_exhausted": _quota_exhausted,
        "voice_id": voice_id(),
        "model": model_id(),
    }


def _cache_path(text: str) -> str:
    key = f"{voice_id()}|{model_id()}|{text}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return os.path.join(_CACHE_DIR, f"{digest}.mp3")


def synthesize(text: str) -> bytes | None:
    """Return MP3 bytes for `text`, or None if unavailable (caller falls back).

    Cached on disk, so repeated phrases (greetings, briefings) cost nothing.
    """
    global _quota_exhausted
    text = (text or "").strip()
    if not text:
        return None

    path = _cache_path(text)
    with _cache_lock:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except Exception:
                pass

    key = _api_key()
    if not key or _quota_exhausted:
        return None

    try:
        resp = requests.post(
            f"{API_BASE}/text-to-speech/{voice_id()}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": model_id(),
                "voice_settings": {
                    "stability": 0.45,       # a little expressive range
                    "similarity_boost": 0.8,
                    "speed": 1.05,           # matches the brisk pace Ahmed wanted
                    "use_speaker_boost": True,
                },
            },
            params={"output_format": "mp3_44100_128"},
            timeout=30,
        )
    except Exception as exc:
        print(f"[tts] request failed: {exc}", flush=True)
        return None

    if resp.status_code == 401:
        print("[tts] rejected: check ELEVENLABS_API_KEY", flush=True)
        return None
    if resp.status_code == 429 or (
        resp.status_code == 402
        or (resp.status_code >= 400 and b"quota" in resp.content.lower())
    ):
        _quota_exhausted = True
        print("[tts] quota exhausted — falling back to the browser voice", flush=True)
        return None
    if resp.status_code >= 400:
        print(f"[tts] error {resp.status_code}: {resp.text[:160]}", flush=True)
        return None

    audio = resp.content
    if not audio:
        return None

    with _cache_lock:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(audio)
        except Exception:
            pass  # cache is an optimisation, not a requirement
    return audio


def subscription() -> dict | None:
    """Remaining character quota, for surfacing usage in the HUD."""
    key = _api_key()
    if not key:
        return None
    try:
        r = requests.get(f"{API_BASE}/user/subscription",
                         headers={"xi-api-key": key}, timeout=10)
        if r.status_code >= 400:
            return None
        d = r.json()
        used = d.get("character_count", 0)
        limit = d.get("character_limit", 0)
        return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
    except Exception:
        return None
