"""Google (Gmail + Calendar + Drive) integration for Jarvis.

One-time local OAuth via InstalledAppFlow: the first call that needs Google
opens a browser for consent, then a refresh token is cached in token.json so
later runs are silent. This is deliberately simpler than Anthropic's hosted MCP
connector, which would need a remote MCP server standing in front of Google's
REST APIs — pointless for a single-user desktop app.

Everything degrades gracefully: if the client libraries aren't installed or
GOOGLE_CALENDAR_CREDENTIALS isn't set, is_available() returns False and Jarvis
simply tells Ahmed the integration isn't connected (never fabricates data).
"""

import base64
import os
from email.mime.text import MIMEText

_HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(_HERE, "token.json")

# Least-privilege-ish: read/draft/send mail, full calendar, read + app-created Drive.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    _LIBS_AVAILABLE = True
except ImportError:
    _LIBS_AVAILABLE = False


def _credentials_path() -> str | None:
    """Path to the OAuth client secrets file (downloaded from Google Cloud)."""
    return os.getenv("GOOGLE_CALENDAR_CREDENTIALS") or None


def is_available() -> bool:
    """True if we could plausibly talk to Google: libs installed and either a
    cached token or a client-secrets file to bootstrap one exists."""
    if not _LIBS_AVAILABLE:
        return False
    if os.path.exists(TOKEN_FILE):
        return True
    creds = _credentials_path()
    return bool(creds and os.path.exists(creds))


_cached_creds = None


def _get_credentials():
    """Return valid OAuth credentials, running the browser flow once if needed.

    Raises RuntimeError with a plain message if the integration can't be set up,
    so the caller can surface it to Ahmed instead of crashing.
    """
    global _cached_creds
    if not _LIBS_AVAILABLE:
        raise RuntimeError(
            "Google client libraries aren't installed. Run: "
            "pip3 install google-api-python-client google-auth-oauthlib"
        )

    creds = _cached_creds
    if creds is None and os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        _cached_creds = creds
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        secrets = _credentials_path()
        if not secrets or not os.path.exists(secrets):
            raise RuntimeError(
                "Google isn't connected. Set GOOGLE_CALENDAR_CREDENTIALS in .env to "
                "your downloaded OAuth client-secrets JSON, then try again."
            )
        flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    _cached_creds = creds
    return creds


_services: dict = {}


def _service(name: str, version: str):
    key = f"{name}:{version}"
    if key not in _services:
        _services[key] = build(name, version, credentials=_get_credentials(),
                                cache_discovery=False)
    return _services[key]


# ── Gmail ─────────────────────────────────────────────────────

def list_unread(max_results: int = 10) -> list[dict]:
    """Return [{id, sender, subject, snippet}] for unread inbox mail."""
    svc = _service("gmail", "v1")
    resp = svc.users().messages().list(
        userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results
    ).execute()
    out = []
    for ref in resp.get("messages", []):
        msg = svc.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        out.append({
            "id": ref["id"],
            "sender": headers.get("From", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": msg.get("snippet", ""),
        })
    return out


def unread_count() -> int:
    """Cheap count of unread inbox mail — one list call, no per-message fetches."""
    svc = _service("gmail", "v1")
    resp = svc.users().messages().list(
        userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
    ).execute()
    return resp.get("resultSizeEstimate", 0)


def search_messages(query: str, max_results: int = 10) -> list[dict]:
    """Gmail search (same query syntax as the Gmail search box)."""
    svc = _service("gmail", "v1")
    resp = svc.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    out = []
    for ref in resp.get("messages", []):
        msg = svc.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        out.append({
            "id": ref["id"],
            "sender": headers.get("From", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        })
    return out


def _decode_body(payload) -> str:
    """Pull a plaintext body out of a Gmail message payload."""
    def walk(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        for sub in part.get("parts", []) or []:
            got = walk(sub)
            if got:
                return got
        return ""
    return walk(payload)


def read_message(message_id: str) -> dict:
    """Full message: {sender, subject, date, body}."""
    svc = _service("gmail", "v1")
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    return {
        "sender": headers.get("From", "(unknown)"),
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "body": _decode_body(msg["payload"]).strip() or msg.get("snippet", ""),
    }


def _build_raw(to: str, subject: str, body: str) -> str:
    mime = MIMEText(body)
    mime["To"] = to
    mime["Subject"] = subject
    return base64.urlsafe_b64encode(mime.as_bytes()).decode()


def create_draft(to: str, subject: str, body: str) -> str:
    svc = _service("gmail", "v1")
    draft = svc.users().drafts().create(
        userId="me", body={"message": {"raw": _build_raw(to, subject, body)}}
    ).execute()
    return draft["id"]


def send_email(to: str, subject: str, body: str) -> str:
    svc = _service("gmail", "v1")
    sent = svc.users().messages().send(
        userId="me", body={"raw": _build_raw(to, subject, body)}
    ).execute()
    return sent["id"]


# ── Calendar ──────────────────────────────────────────────────

def list_events(time_min_iso: str, time_max_iso: str, max_results: int = 20) -> list[dict]:
    svc = _service("calendar", "v3")
    resp = svc.events().list(
        calendarId="primary", timeMin=time_min_iso, timeMax=time_max_iso,
        singleEvents=True, orderBy="startTime", maxResults=max_results,
    ).execute()
    out = []
    for ev in resp.get("items", []):
        start = ev.get("start", {})
        out.append({
            "id": ev["id"],
            "summary": ev.get("summary", "(no title)"),
            "start": start.get("dateTime") or start.get("date", ""),
            "location": ev.get("location", ""),
        })
    return out


def create_event(summary: str, start_iso: str, end_iso: str,
                 description: str = "", location: str = "") -> str:
    svc = _service("calendar", "v3")
    body = {
        "summary": summary,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    ev = svc.events().insert(calendarId="primary", body=body).execute()
    return ev.get("htmlLink", ev["id"])


def delete_event(event_id: str) -> None:
    svc = _service("calendar", "v3")
    svc.events().delete(calendarId="primary", eventId=event_id).execute()


# ── Drive ─────────────────────────────────────────────────────

def search_files(query: str, max_results: int = 10) -> list[dict]:
    svc = _service("drive", "v3")
    resp = svc.files().list(
        q=f"name contains '{query}' and trashed = false",
        pageSize=max_results, fields="files(id, name, mimeType, modifiedTime)",
    ).execute()
    return resp.get("files", [])


def read_file(file_id: str) -> str:
    """Return the text content of a Drive file (Google Docs exported to text)."""
    svc = _service("drive", "v3")
    meta = svc.files().get(fileId=file_id, fields="mimeType, name").execute()
    if meta["mimeType"].startswith("application/vnd.google-apps"):
        data = svc.files().export(fileId=file_id, mimeType="text/plain").execute()
    else:
        data = svc.files().get_media(fileId=file_id).execute()
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)


def create_doc(title: str, content: str) -> str:
    """Create a plain-text file in Drive; return its web link."""
    svc = _service("drive", "v3")
    from googleapiclient.http import MediaInMemoryUpload
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
    f = svc.files().create(
        body={"name": title}, media_body=media, fields="id, webViewLink",
    ).execute()
    return f.get("webViewLink", f["id"])
