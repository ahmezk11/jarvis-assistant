"""Notion integration for Jarvis.

Uses an internal-integration token (NOTION_TOKEN in .env) rather than OAuth —
for a single-user desktop app that's the simplest path: create an integration
at notion.so/my-integrations, share the target pages/database with it, paste the
token. Degrades gracefully: no token or no client library → is_available() False
and Jarvis says Notion isn't connected instead of fabricating anything.
"""

import os

try:
    from notion_client import Client
    _LIB_AVAILABLE = True
except ImportError:
    _LIB_AVAILABLE = False


def _token() -> str | None:
    return os.getenv("NOTION_TOKEN") or None


def is_available() -> bool:
    return _LIB_AVAILABLE and bool(_token())


_client = None


def _get_client():
    global _client
    if not _LIB_AVAILABLE:
        raise RuntimeError(
            "The notion-client package isn't installed. Run: pip3 install notion-client"
        )
    if not _token():
        raise RuntimeError(
            "Notion isn't connected. Set NOTION_TOKEN in .env to your integration token."
        )
    if _client is None:
        _client = Client(auth=_token())
    return _client


def search(query: str, max_results: int = 10) -> list[dict]:
    """Search pages/databases the integration can see."""
    client = _get_client()
    resp = client.search(query=query, page_size=max_results)
    out = []
    for r in resp.get("results", []):
        title = "(untitled)"
        props = r.get("properties", {})
        # Page title lives under whichever property has type == "title".
        for prop in props.values():
            if prop.get("type") == "title" and prop["title"]:
                title = "".join(t.get("plain_text", "") for t in prop["title"])
                break
        out.append({
            "id": r["id"],
            "type": r.get("object", "page"),
            "title": title,
            "url": r.get("url", ""),
        })
    return out


def read_page(page_id: str, max_blocks: int = 50) -> str:
    """Return the plain text of a page's top-level blocks."""
    client = _get_client()
    resp = client.blocks.children.list(block_id=page_id, page_size=max_blocks)
    lines = []
    for block in resp.get("results", []):
        btype = block.get("type", "")
        rich = block.get(btype, {}).get("rich_text", []) if isinstance(block.get(btype), dict) else []
        text = "".join(t.get("plain_text", "") for t in rich)
        if text:
            lines.append(text)
    return "\n".join(lines) if lines else "(page has no readable text blocks)"


def create_page(parent_id: str, title: str, content: str = "") -> str:
    """Create a page under a parent page. Returns the new page URL.

    parent_id is the ID of an existing page shared with the integration.
    """
    client = _get_client()
    children = []
    if content:
        children = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
        }]
    page = client.pages.create(
        parent={"page_id": parent_id},
        properties={"title": [{"type": "text", "text": {"content": title}}]},
        children=children,
    )
    return page.get("url", page["id"])
